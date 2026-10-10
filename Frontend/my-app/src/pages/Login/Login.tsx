import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { GoogleLogin } from "@react-oauth/google";
import { useAuth } from "../../auth/AuthContext";
import sonarLogo from "../../assets/sonar-logo.png";
import "./Login.css";

const HAS_GOOGLE_ID = Boolean(import.meta.env.VITE_GOOGLE_CLIENT_ID);

export default function Login() {
  const { user, loginWithGoogle, loginAsGuest } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");

  if (user) return <Navigate to="/" replace />;

  return (
    <div className="lg-page">
      <aside className="lg-side">
        <div className="lg-side-inner">
          <h2>Turn test results into clear reports</h2>
          <p>Upload your k6 or JMeter report and get a PDF that developers, testers and managers can all read.</p>
          <ul>
            <li>Executive summary in plain English</li>
            <li>Key performance numbers at a glance</li>
            <li>Risks and recommendations</li>
          </ul>
        </div>
      </aside>

      <main className="lg-main">
        <div className="lg-card">
          <img src={sonarLogo} alt="Sonar" className="lg-logo" />
          <h1>Welcome back</h1>
          <p className="lg-sub">Sign in to continue to your reports</p>

          {HAS_GOOGLE_ID ? (
            <div className="lg-google">
              <GoogleLogin
                onSuccess={(res) => {
                  if (res.credential) {
                    loginWithGoogle(res.credential);
                    navigate("/");
                  }
                }}
                onError={() => setError("Google sign-in failed. Please try again.")}
                theme="outline"
                size="large"
                shape="pill"
                text="continue_with"
                width="320"
              />
            </div>
          ) : (
            <div className="lg-note">
              Google sign-in isn't configured yet. Add <code>VITE_GOOGLE_CLIENT_ID</code> to your <code>.env</code> file.
            </div>
          )}

          {error && <div className="lg-error">{error}</div>}

          <div className="lg-divider"><span>or</span></div>

          <button
            className="lg-guest"
            onClick={() => {
              loginAsGuest();
              navigate("/");
            }}
          >
            Continue as guest
          </button>

          <p className="lg-foot">By continuing you agree to our terms and privacy policy.</p>
        </div>
      </main>
    </div>
  );
}