"""
TalentLens — Stage 3: Embedding & retrieval.

Embeds every parsed resume's raw text with all-MiniLM-L6-v2, indexes the vectors in
FAISS (cosine similarity via normalized inner product), and — given a selected JD —
retrieves the Top-K most similar resumes. This is the only stage that touches the
entire resume pool; it's indexed, not a linear scan, so it stays fast as the pool grows.

Run: python3 stage3_embed_index.py            # builds/rebuilds the index
Run: python3 stage3_embed_index.py <job_id>    # builds (if needed) then retrieves for a JD
"""
import json
import logging
import sys

import faiss
import numpy as np

from config import (
    LOG_DIR,
    FAISS_INDEX_PATH,
    RESUME_ID_MAP_PATH,
    TOP_K_RETRIEVAL,
)
from db import init_db, get_connection

LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "stage3.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("stage3")

_model = None  # lazy-loaded singleton — loading is cheap (offline, <1s) but avoid repeat imports


def get_model():
    global _model
    if _model is None:
        import gt_all_minilm_l6_v2
        from sentence_transformers import SentenceTransformer

        model_path = str(gt_all_minilm_l6_v2.get_model_path())
        _model = SentenceTransformer(model_path)
        log.info("Loaded all-MiniLM-L6-v2 from offline bundle (gt-all-minilm-l6-v2)")
    return _model


def embed_texts(texts):
    model = get_model()
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    # normalize so inner product == cosine similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1e-8
    return (embeddings / norms).astype("float32")


def build_resume_index():
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT resume_id, raw_text FROM resumes WHERE parse_status = 'OK' AND raw_text IS NOT NULL AND raw_text != ''"
    ).fetchall()
    conn.close()

    resume_ids = [r["resume_id"] for r in rows]
    texts = [r["raw_text"] for r in rows]
    log.info(f"Embedding {len(texts)} resumes...")

    embeddings = embed_texts(texts)
    dim = embeddings.shape[1]

    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    faiss.write_index(index, str(FAISS_INDEX_PATH))
    with open(RESUME_ID_MAP_PATH, "w") as f:
        json.dump(resume_ids, f)

    log.info(f"Stage 3 index built: {index.ntotal} resumes, dim={dim}. "
             f"Saved to {FAISS_INDEX_PATH}")
    return index.ntotal


def load_index():
    index = faiss.read_index(str(FAISS_INDEX_PATH))
    with open(RESUME_ID_MAP_PATH) as f:
        resume_ids = json.load(f)
    return index, resume_ids


def retrieve_top_k(jd_text: str, k: int = TOP_K_RETRIEVAL):
    """Given JD text, return [(resume_id, similarity_score), ...] sorted descending."""
    index, resume_ids = load_index()
    query_emb = embed_texts([jd_text])
    k = min(k, index.ntotal)
    scores, indices = index.search(query_emb, k)
    results = [
        (resume_ids[idx], float(score))
        for idx, score in zip(indices[0], scores[0])
        if idx != -1
    ]
    return results


def retrieve_for_job_id(job_id: str, k: int = TOP_K_RETRIEVAL):
    conn = get_connection()
    row = conn.execute(
        "SELECT job_id, job_title, job_description, skills, experience, qualifications "
        "FROM job_descriptions WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    conn.close()
    if row is None:
        raise ValueError(f"No job_description found for job_id={job_id}")

    # combine title + description + skills for a richer query embedding
    jd_text = f"{row['job_title']}. {row['job_description']} Skills: {row['skills']}"
    results = retrieve_top_k(jd_text, k=k)
    return row, results


if __name__ == "__main__":
    n = build_resume_index()
    log.info(f"Index build complete: {n} resumes indexed")

    if len(sys.argv) > 1:
        job_id = sys.argv[1]
        jd_row, results = retrieve_for_job_id(job_id)
        print(f"\nTop {len(results)} matches for JD {job_id} — {jd_row['job_title']}:")
        for resume_id, score in results[:10]:
            print(f"  {resume_id}: {score:.4f}")
