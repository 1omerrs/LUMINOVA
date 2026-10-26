import { BrowserRouter, Route, Routes } from "react-router";
import { WorkspaceShell } from "./components/workspace/WorkspaceShell.tsx";
import { ForgotPasswordPage } from "./pages/ForgotPasswordPage.tsx";
import { PublicQuotePage } from "./pages/PublicQuotePage.tsx";
import { LandingPage } from "./pages/LandingPage.tsx";
import { LoginPage } from "./pages/LoginPage.tsx";
import { NotFoundPage } from "./pages/NotFoundPage.tsx";
import { RegisterPage } from "./pages/RegisterPage.tsx";
import { ResetPasswordPage } from "./pages/ResetPasswordPage.tsx";
import { SetupPage } from "./pages/SetupPage.tsx";
import { InvitePage } from "./pages/InvitePage.tsx";
import { StatusPage } from "./pages/StatusPage.tsx";
import { VerifyPage } from "./pages/VerifyPage.tsx";
import { HomePage } from "./pages/workspace/HomePage.tsx";
import { ModulePage } from "./pages/workspace/ModulePage.tsx";
import { ActivityPage } from "./pages/workspace/ActivityPage.tsx";
import { ProfilePage } from "./pages/workspace/ProfilePage.tsx";
import { SupportPage } from "./pages/workspace/SupportPage.tsx";
import { AdminPage } from "./pages/admin/AdminPage.tsx";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/kayit" element={<RegisterPage />} />
        <Route path="/giris" element={<LoginPage />} />
        <Route path="/dogrula" element={<VerifyPage />} />
        <Route path="/sifremi-unuttum" element={<ForgotPasswordPage />} />
        <Route path="/sifre-sifirla" element={<ResetPasswordPage />} />
        <Route path="/kurulum" element={<SetupPage />} />
        <Route path="/davet" element={<InvitePage />} />
        <Route path="/teklif/:token" element={<PublicQuotePage />} />
        <Route path="/panel" element={<WorkspaceShell />}>
          <Route index element={<HomePage />} />
          <Route path="profil" element={<ProfilePage />} />
          <Route path="aktiviteler" element={<ActivityPage />} />
          <Route path="destek" element={<SupportPage />} />
          <Route path=":modulePath" element={<ModulePage />} />
        </Route>
        <Route path="/yonetim" element={<AdminPage />} />
        <Route path="/durum" element={<StatusPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  );
}
