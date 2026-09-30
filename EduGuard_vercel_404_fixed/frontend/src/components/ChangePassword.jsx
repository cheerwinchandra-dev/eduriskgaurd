import { KeyRound } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import PasswordField from "./PasswordField";

/** Change-your-own-password dialog. `forced` (a temporary password is in use) can't be dismissed. */
export default function ChangePassword({ forced = false, onDone, onClose }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (next !== again) { setError("The two new passwords don't match."); return; }
    setBusy(true);
    try {
      onDone(await api.post("/api/auth/password", { current, new: next }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-labelledby="pw-title">
      <form className="card w-full max-w-md space-y-4 p-6" onSubmit={submit}>
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-lg bg-brand/10 text-brand dark:text-brand-light"><KeyRound size={20} /></span>
          <div>
            <h2 id="pw-title" className="text-lg font-semibold">{forced ? "Choose your own password" : "Change password"}</h2>
            {forced && <p className="muted text-sm">You signed in with a temporary password. Set a private one to continue.</p>}
          </div>
        </div>
        <div><label className="label" htmlFor="pw-cur">{forced ? "Temporary password" : "Current password"}</label>
          <PasswordField id="pw-cur" value={current} onChange={(e) => setCurrent(e.target.value)} /></div>
        <div><label className="label" htmlFor="pw-new">New password</label>
          <PasswordField id="pw-new" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" placeholder="At least 8 characters" /></div>
        <div><label className="label" htmlFor="pw-again">Repeat new password</label>
          <PasswordField id="pw-again" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" /></div>
        {error && <p className="text-sm text-elev" role="alert">{error}</p>}
        <div className="flex justify-end gap-2">
          {!forced && <button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>}
          <button className="btn btn-primary" disabled={busy}>{busy ? "Saving" : "Save password"}</button>
        </div>
      </form>
    </div>
  );
}
