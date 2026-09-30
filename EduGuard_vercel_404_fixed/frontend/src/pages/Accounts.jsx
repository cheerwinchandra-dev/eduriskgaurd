import { CheckCircle2, Copy, KeyRound, Power, Trash2, UserPlus } from "lucide-react";
import { useState } from "react";
import PasswordField from "../components/PasswordField";
import { Card, Empty, ErrorNote, Loading, Notice, PageTitle } from "../components/ui";
import { api, fmt } from "../lib/api";
import { useApi } from "../lib/hooks";

const BLANK = { full_name: "", username: "", role: "faculty", password: "" };

export default function Accounts({ roles, me }) {
  const users = useApi("/api/users");
  const [form, setForm] = useState(BLANK);
  const [created, setCreated] = useState(null); // { username, password, kind }
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [copied, setCopied] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  if (users.loading && !users.data) return <Loading />;
  if (users.error) return <ErrorNote error={users.error} retry={users.reload} />;

  const act = async (key, fn, after) => {
    setBusy(key); setError("");
    try { const res = await fn(); if (after) after(res); users.reload(); }
    catch (e) { setError(e.message); }
    finally { setBusy(""); }
  };

  const create = (e) => {
    e.preventDefault();
    act("create", () => api.post("/api/users", { ...form, password: form.password || undefined }), (res) => {
      setCreated({ username: res.user.username, password: res.password, kind: "created", name: res.user.full_name });
      setForm(BLANK); setCopied(false);
    });
  };

  const reset = (u) => {
    if (!window.confirm(`Reset the password for ${u.full_name}? They will be signed out and must choose a new password.`)) return;
    act(`pw${u.id}`, () => api.post(`/api/users/${u.id}/password`, {}), (res) => {
      setCreated({ username: u.username, password: res.password, kind: "reset", name: u.full_name }); setCopied(false);
    });
  };

  const toggle = (u) => {
    if (u.active && !window.confirm(`Switch off ${u.full_name}'s account? They will be signed out.`)) return;
    act(`on${u.id}`, () => api.patch(`/api/users/${u.id}`, { active: !u.active }));
  };

  const remove = (u) => {
    if (!window.confirm(`Delete ${u.full_name}'s account permanently? Their past actions stay in the access log.`)) return;
    act(`del${u.id}`, () => api.del(`/api/users/${u.id}`));
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(`Username: ${created.username}\nTemporary password: ${created.password}`);
      setCopied(true);
    } catch { setError("Couldn't copy. Select the text and copy it by hand."); }
  };

  const list = users.data || [];

  return (
    <>
      <PageTitle title="Accounts">Create sign-ins for administrators, faculty and equity reviewers, and manage who has access. Only academic advisors can see this page.</PageTitle>

      {error && <Notice tone="warn">{error}</Notice>}
      {created && (
        <div className="mb-5 rounded-xl border border-low/40 bg-low/10 p-4 text-sm" role="status">
          <p className="flex items-center gap-2 font-medium">
            <CheckCircle2 size={16} className="text-low" />
            {created.kind === "created" ? `Account created for ${created.name}.` : `New temporary password for ${created.name}.`}
          </p>
          <p className="mt-2">Username <code className="rounded bg-white/70 px-1.5 py-0.5 dark:bg-white/10">{created.username}</code>{" "}
            Temporary password <code className="rounded bg-white/70 px-1.5 py-0.5 font-semibold dark:bg-white/10">{created.password}</code></p>
          <p className="muted mt-2">Share this privately. It is shown only now, and they must choose their own password when they first sign in.</p>
          <div className="mt-3 flex gap-2">
            <button className="btn btn-quiet" onClick={copy}><Copy size={15} /> {copied ? "Copied" : "Copy"}</button>
            <button className="btn btn-ghost" onClick={() => setCreated(null)}>Done</button>
          </div>
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-3">
        <Card title="Add a person" subtitle="They sign in on the page for the role you choose." className="xl:col-span-1">
          <form className="space-y-4" onSubmit={create}>
            <div><label className="label" htmlFor="ac-name">Full name</label>
              <input id="ac-name" className="input" value={form.full_name} onChange={set("full_name")} required maxLength={80} /></div>
            <div><label className="label" htmlFor="ac-user">Username</label>
              <input id="ac-user" className="input" value={form.username} onChange={set("username")} required maxLength={32} autoComplete="off" />
              <p className="muted mt-1 text-xs">3 to 32 characters: letters, numbers, dot, dash, underscore.</p></div>
            <div><label className="label" htmlFor="ac-role">Role</label>
              <select id="ac-role" className="input" value={form.role} onChange={set("role")}>
                {Object.entries(roles).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
              </select></div>
            <div><label className="label" htmlFor="ac-pw">Temporary password</label>
              <PasswordField id="ac-pw" value={form.password} onChange={set("password")} autoComplete="new-password" required={false}
                placeholder="Leave blank to generate one" /></div>
            <button className="btn btn-primary w-full" disabled={busy === "create"}><UserPlus size={16} /> {busy === "create" ? "Creating" : "Create account"}</button>
          </form>
        </Card>

        <Card title="People with access" subtitle={`${list.length} account${list.length === 1 ? "" : "s"}`} pad={false} className="xl:col-span-2">
          {list.length === 0 ? <Empty title="No accounts yet" /> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-sm">
                <thead><tr className="border-b border-slate-200 dark:border-slate-700/60">
                  <th className="th">Name</th><th className="th">Role</th><th className="th">Status</th><th className="th">Last sign-in</th><th className="th text-right">Actions</th>
                </tr></thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-700/40">
                  {list.map((u) => {
                    const self = u.id === me.id;
                    return (
                      <tr key={u.id}>
                        <td className="td"><p className="font-medium">{u.full_name}{self && <span className="muted font-normal"> (you)</span>}</p><p className="muted text-xs">{u.username}</p></td>
                        <td className="td">
                          <select className="input w-auto py-1" value={u.role} disabled={self || busy === `role${u.id}`} aria-label={`Role for ${u.full_name}`}
                            onChange={(e) => act(`role${u.id}`, () => api.patch(`/api/users/${u.id}`, { role: e.target.value }))}>
                            {Object.entries(roles).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
                          </select>
                        </td>
                        <td className="td">
                          <span className={`pill ${u.active ? "pill-low" : "pill-unavailable"}`}>{u.active ? "Active" : "Switched off"}</span>
                          {u.must_change && u.active && <p className="muted mt-1 text-xs">Hasn't set own password</p>}
                        </td>
                        <td className="td muted">{u.last_login ? fmt.dateTime(u.last_login) : "Never"}</td>
                        <td className="td">
                          <div className="flex justify-end gap-1">
                            <button className="btn btn-quiet px-2.5" onClick={() => reset(u)} disabled={Boolean(busy)} title="Reset password" aria-label={`Reset password for ${u.full_name}`}><KeyRound size={15} /></button>
                            <button className="btn btn-quiet px-2.5" onClick={() => toggle(u)} disabled={self || Boolean(busy)} title={u.active ? "Switch off" : "Switch on"} aria-label={`${u.active ? "Switch off" : "Switch on"} ${u.full_name}`}><Power size={15} /></button>
                            <button className="btn btn-danger px-2.5" onClick={() => remove(u)} disabled={self || Boolean(busy)} title="Delete" aria-label={`Delete ${u.full_name}`}><Trash2 size={15} /></button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
