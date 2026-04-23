export default function Footer() {
  return (
    <footer className="border-t border-[#1C1C1C] py-8 px-5">
      <div className="max-w-4xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
        <span className="text-[#00C896] font-mono font-bold text-sm tracking-tight">
          BetMate
        </span>

        <p className="text-[#888888] text-[11px] text-center font-mono leading-relaxed">
          Informational only. Gamble responsibly. 18+
          <span className="mx-2 text-[#333]">·</span>
          AU helpline: 1800 858 858
        </p>

        <div className="flex items-center gap-5 text-[11px] text-[#888888] font-mono">
          <a href="#" className="hover:text-white transition-colors">Privacy</a>
          <a href="#" className="hover:text-white transition-colors">Terms</a>
          <a href="#" className="hover:text-white transition-colors">Contact</a>
        </div>
      </div>
    </footer>
  );
}
