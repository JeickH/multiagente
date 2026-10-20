import { DEMO_UI } from '../../lib/demo_copy';

/** Título y «cómo funciona» en 3 pasos (zona `DemoIntro` del wireframe). */
export default function DemoIntro() {
  const t = DEMO_UI.intro;
  return (
    <div className="md:pt-6">
      <h1 className="font-heading font-extrabold text-[28px] leading-[1.1] md:text-5xl md:leading-[1.08] mt-2 md:mt-0 text-white">
        <span>{t.titulo}</span> <span className="block text-gloma-mint">{t.titulo2}</span>
      </h1>
      <p className="mt-3 md:mt-5 text-[15px] md:text-lg font-light text-white/85 max-w-md">{t.subtitulo}</p>
      <ol
        className="mt-5 md:mt-10 flex md:flex-col gap-2 md:gap-5 text-[12px] md:text-[15px]"
        aria-label="Cómo funciona la demo"
      >
        {t.pasos.map((p, i) => (
          <li
            key={p.titulo}
            className="flex items-center gap-2 md:gap-4 flex-1 md:flex-none rounded-2xl md:rounded-none bg-white/[0.04] md:bg-transparent px-2.5 py-2 md:p-0"
          >
            <span
              className={`w-6 h-6 md:w-10 md:h-10 rounded-full font-heading font-bold flex items-center justify-center shrink-0 text-xs md:text-base ${
                i === 0 ? 'bg-gloma-mint text-gloma-ink' : 'border border-gloma-mint text-gloma-mint'
              }`}
              aria-hidden="true"
            >
              {i + 1}
            </span>
            <span>
              <b className="font-semibold text-white">{p.titulo}</b>
              <span className="hidden md:inline text-gloma-ink-muted"> · {p.detalle}</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
