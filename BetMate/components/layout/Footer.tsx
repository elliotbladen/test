export default function Footer() {
  return (
    <footer className="hidden lg:block border-t border-[#1E1E1E] py-8 px-5 bg-[#0D0D0D]">
      <div className="max-w-4xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
        <span className="font-bold text-sm tracking-tight">
          <span className="text-white">Bet</span>
          <span className="text-[#00C896]">Mate</span>
        </span>

        <p className="text-[#5C5C5C] text-[11px] text-center font-mono leading-relaxed">
          Informational only. Gamble responsibly. 18+
          <span className="mx-2 text-[#252525]">·</span>
          AU helpline: 1800 858 858
        </p>

        <div className="flex items-center gap-5 text-[11px] text-[#5C5C5C] font-mono">
          <a href="#" className="hover:text-white transition-colors">Privacy</a>
          <a href="#" className="hover:text-white transition-colors">Terms</a>
          <a href="#" className="hover:text-white transition-colors">Contact</a>
        </div>
      </div>
    </footer>
  );
}
