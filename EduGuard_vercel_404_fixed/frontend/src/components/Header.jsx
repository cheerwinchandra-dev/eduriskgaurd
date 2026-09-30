import { KeyRound, LogOut, Menu, Moon, Search, Sun } from "lucide-react";
import { useState } from "react";

export default function Header({ title, onMenu, onSearch, canSearch, user, roleName, onPassword, onSignOut, dark, onDark }) {
  const [text, setText] = useState("");
  return (
    <header className="print-hide sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur dark:border-slate-700/60 dark:bg-night/90 sm:px-6">
      <button className="btn btn-quiet px-2.5 lg:hidden" onClick={onMenu} aria-label="Open menu"><Menu size={18} /></button>
      <h2 className="hidden min-w-0 flex-1 truncate font-display text-lg font-semibold md:block">{title}</h2>

      {canSearch && (
        <form className="relative w-full max-w-xs" onSubmit={(e) => { e.preventDefault(); onSearch(text.trim()); }} role="search">
          <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className="input pl-9" placeholder="Search student ID or program" value={text}
            onChange={(e) => setText(e.target.value)} aria-label="Search students" />
        </form>
      )}

      <div className="ml-auto flex items-center gap-2 sm:gap-3">
        <div className="hidden text-right text-sm leading-tight md:block" title={`Signed in as ${user.username}`}>
          <p className="font-medium">{user.full_name}</p>
          <p className="muted text-xs">{roleName}</p>
        </div>
        <button className="btn btn-quiet px-2.5" onClick={onPassword} aria-label="Change password" title="Change password"><KeyRound size={18} /></button>
        <button className="btn btn-quiet px-2.5" onClick={onDark} aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}>
          {dark ? <Sun size={18} /> : <Moon size={18} />}
        </button>
        <button className="btn btn-quiet" onClick={onSignOut}><LogOut size={16} /> <span className="hidden sm:inline">Sign out</span></button>
      </div>
    </header>
  );
}
