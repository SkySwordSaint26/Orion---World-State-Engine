import React, { useEffect, useState } from 'react';
import { Dialog } from './Dialog';
import { useNavigate } from 'react-router-dom';
import { changePassword, getProfile, updateProfile } from '../api/account';
import type { Profile } from '../api/account';
import { useAuthStore } from '../store/useAuthStore';

const field = 'w-full bg-surface-container-lowest border border-starlight-white/10 rounded-lg px-3 py-2 text-sm text-starlight-white focus:border-primary focus:outline-none';
const label = 'font-label-sm text-[10px] uppercase tracking-widest text-on-surface-variant/60 mb-1 block';

/** Creator profile: pen name, account, what you have written so far, password and sign-out. */
export const CreatorProfileModal: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const navigate = useNavigate();
  const { logout } = useAuthStore();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [name, setName] = useState('');
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [pwMessage, setPwMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    getProfile()
      .then((p) => { setProfile(p); setName(p.display_name); })
      .catch((e) => setError(e.message));
  }, []);

  const saveName = async () => {
    try {
      const p = await updateProfile({ display_name: name });
      setProfile(p);
      setName(p.display_name);
      setError(null);
      setSaved('Saved');
      setTimeout(() => setSaved(null), 2000);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const savePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (next.length < 8) {
      setPwMessage({ ok: false, text: 'The new password needs at least 8 characters.' });
      return;
    }
    try {
      await changePassword(current, next);
      setPwMessage({ ok: true, text: 'Password changed.' });
      setCurrent('');
      setNext('');
    } catch (err: any) {
      setPwMessage({ ok: false, text: err.message });
    }
  };

  const signOut = () => {
    logout();
    navigate('/signin');
  };

  return (
    <Dialog title="Creator Profile" onClose={onClose}>
        {error && <p className="px-6 pt-4 text-sm text-red-300">{error}</p>}
        {!profile && !error && <p className="p-6 text-sm text-on-surface-variant/60">Loading…</p>}

        {profile && (
          <div className="space-y-6">
            <section>
              <span className={label}>Pen name</span>
              <div className="flex gap-2">
                <input aria-label="Pen name" className={field} value={name} placeholder="How you sign your work" onChange={(e) => setName(e.target.value)} />
                <button onClick={saveName} className="px-4 rounded-lg text-sm bg-primary/20 text-primary border border-primary/50 hover:bg-primary hover:text-void-black transition-colors">
                  {saved ?? 'Save'}
                </button>
              </div>
            </section>

            <section className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className={label}>Email</span>
                <span className="text-starlight-white">{profile.email}</span>
              </div>
              <div>
                <span className={label}>Writing since</span>
                <span className="text-starlight-white">{new Date(profile.created_at).toLocaleDateString()}</span>
              </div>
            </section>

            <section>
              <span className={label}>Your archive</span>
              <div className="grid grid-cols-4 gap-2 text-center">
                {([['Worlds', profile.stats.worlds], ['Manuscripts', profile.stats.manuscripts],
                   ['Chapters', profile.stats.chapters], ['Entities', profile.stats.entities]] as const).map(([k, v]) => (
                  <div key={k} className="rounded-lg border border-starlight-white/5 bg-surface-container-low py-3">
                    <div className="text-lg text-starlight-white font-semibold">{v}</div>
                    <div className="text-[10px] uppercase tracking-wider text-on-surface-variant/60">{k}</div>
                  </div>
                ))}
              </div>
            </section>

            <form onSubmit={savePassword} className="space-y-2">
              <span className={label}>Change password</span>
              <input type="password" className={field} placeholder="Current password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" />
              <input type="password" className={field} placeholder="New password (8+ characters)" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" />
              <div className="flex items-center justify-between">
                <span className={`text-xs ${pwMessage?.ok ? 'text-emerald-400' : 'text-red-300'}`}>{pwMessage?.text}</span>
                <button type="submit" disabled={!current || !next} className="px-4 py-1.5 rounded-lg text-sm bg-primary/20 text-primary border border-primary/50 hover:bg-primary hover:text-void-black transition-colors disabled:opacity-40">
                  Change password
                </button>
              </div>
            </form>

            <div className="pt-4 border-t border-starlight-white/5 flex justify-end">
              <button onClick={signOut} className="px-4 py-1.5 rounded-lg text-sm text-starlight-white/70 hover:text-red-300 hover:bg-surface-container-highest transition-colors flex items-center gap-1.5">
                <span className="material-symbols-outlined text-[18px]">logout</span> Sign out
              </button>
            </div>
          </div>
        )}
    </Dialog>
  );
};
