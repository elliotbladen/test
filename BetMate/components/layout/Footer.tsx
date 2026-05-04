export default function Footer() {
  return (
    <footer className="hidden lg:block border-t border-[#E2E8F0] py-8 px-5 bg-white">
      <div className="max-w-4xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
        <span className="font-display font-extrabold text-sm tracking-tight">
          <span className="text-[#111827]">Bet</span>
          <span className="text-[#00C896]">Mate</span>
        </span>

        <p className="text-[#9CA3AF] text-[11px] text-center font-mono leading-relaxed">
          Informational only. Gamble responsibly. 18+
          <span className="mx-2 text-[#D1D5DB]">·</span>
          AU helpline: 1800 858 858
        </p>

        <div className="flex items-center gap-5 text-[11px] text-[#9CA3AF] font-mono">
          <a href="#" className="hover:text-[#111827] transition-colors">Privacy</a>
          <a href="#" className="hover:text-[#111827] transition-colors">Terms</a>
          <a href="#" className="hover:text-[#111827] transition-colors">Contact</a>
        </div>
      </div>
    </footer>
  );
}
