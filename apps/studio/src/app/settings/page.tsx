import { MainLayout } from "@/components/layout/main-layout";
import { Settings } from "lucide-react";

export default function SettingsPage() {
  return (
    <MainLayout>
      <div className="flex flex-col gap-6 p-6">
        <header>
          <div className="flex items-center gap-3 mb-2">
            <Settings className="h-6 w-6 text-primary" />
            <h1 className="text-2xl font-bold">Settings</h1>
          </div>
          <p className="text-sm text-muted-foreground terminal-text">
            Configure your entropy quantization environment
          </p>
        </header>

        <section className="ceq-card">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <span className="text-primary">›</span>
            API Configuration
          </h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between py-2 border-b border-border">
              <div>
                <p className="font-medium">API Endpoint</p>
                <p className="text-sm text-muted-foreground font-mono">
                  {process.env.NEXT_PUBLIC_API_URL || "http://localhost:5800"}
                </p>
              </div>
              <span className="text-xs px-2 py-1 bg-green-500/10 text-green-500 rounded">
                Connected
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b border-border">
              <div>
                <p className="font-medium">Version</p>
                <p className="text-sm text-muted-foreground font-mono">ceq v0.1.0</p>
              </div>
            </div>
          </div>
        </section>

        <section className="ceq-card">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <span className="text-primary">›</span>
            Preferences
          </h2>
          <div className="text-center py-8 text-muted-foreground">
            <Settings className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p className="terminal-text">Preferences module loading...</p>
            <p className="text-sm">User preferences will be configurable here.</p>
          </div>
        </section>
      </div>
    </MainLayout>
  );
}
