import { Sidebar } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";
import { ScreeningProvider } from "@/lib/screening-context";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <ScreeningProvider>
      <div className="flex min-h-screen w-full bg-background">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <Topbar />
          <main className="flex-1 max-w-[1400px] w-full mx-auto px-6 py-6">{children}</main>
        </div>
      </div>
    </ScreeningProvider>
  );
}
