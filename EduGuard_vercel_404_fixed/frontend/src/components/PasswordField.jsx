import { Eye, EyeOff } from "lucide-react";
import { useState } from "react";

/** Password input with a show/hide button. */
export default function PasswordField({ id, value, onChange, autoComplete = "current-password", placeholder, required = true }) {
  const [shown, setShown] = useState(false);
  return (
    <div className="relative">
      <input id={id} type={shown ? "text" : "password"} className="input pr-10" value={value} onChange={onChange}
        autoComplete={autoComplete} placeholder={placeholder} required={required} maxLength={128} />
      <button type="button" onClick={() => setShown(!shown)} aria-label={shown ? "Hide password" : "Show password"}
        className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200">
        {shown ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </div>
  );
}
