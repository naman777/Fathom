import type { SVGProps } from "react";

const base = (p: SVGProps<SVGSVGElement>) => ({
  width: 16,
  height: 16,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  ...p,
});

export const Logo = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base({ width: 28, height: 28, ...p })} viewBox="0 0 32 32" stroke="none">
    <defs>
      <linearGradient id="lg" x1="0" y1="0" x2="32" y2="32">
        <stop stopColor="#8b9bff" />
        <stop offset="1" stopColor="#5b6cf5" />
      </linearGradient>
    </defs>
    <rect width="32" height="32" rx="9" fill="url(#lg)" />
    <path d="M9 22V10h10M9 16h7" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    <circle cx="22.5" cy="21.5" r="2.4" fill="#fff" />
  </svg>
);
export const Plus = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M12 5v14M5 12h14" /></svg>;
export const Send = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M12 19V5M5 12l7-7 7 7" /></svg>;
export const Stop = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)} fill="currentColor" stroke="none"><rect x="6" y="6" width="12" height="12" rx="2.5" /></svg>;
export const Upload = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M12 16V4M6 10l6-6 6 6M4 20h16" /></svg>;
export const File = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></svg>;
export const Trash = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" /></svg>;
export const Download = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M12 4v11M7 11l5 5 5-5M5 20h14" /></svg>;
export const Sun = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>;
export const Moon = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M21 13A9 9 0 1 1 11 3a7 7 0 0 0 10 10z" /></svg>;
export const Chevron = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M9 6l6 6-6 6" /></svg>;
export const Close = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M6 6l12 12M18 6L6 18" /></svg>;
export const Copy = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V6a2 2 0 0 1 2-2h9" /></svg>;
export const Check = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M5 12l5 5 9-10" /></svg>;
export const Sparkle = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M12 3l2 5 5 2-5 2-2 5-2-5-5-2 5-2z" /></svg>;
export const Search = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>;
export const Branch = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><circle cx="6" cy="5" r="2" /><circle cx="6" cy="19" r="2" /><circle cx="18" cy="9" r="2" /><path d="M6 7v10M18 11c0 4-6 3-12 6" /></svg>;
export const Eye = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></svg>;
export const Menu = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M4 7h16M4 12h16M4 17h16" /></svg>;
export const Alert = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M12 9v4M12 17h.01" /><path d="M10.3 3.9L2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /></svg>;

export const Paperclip = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M21 11.5l-8.6 8.6a5.5 5.5 0 01-7.8-7.8l8.6-8.6a3.7 3.7 0 015.2 5.2l-8.6 8.6a1.8 1.8 0 01-2.6-2.6l7.9-7.9" /></svg>;
