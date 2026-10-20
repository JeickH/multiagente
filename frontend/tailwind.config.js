module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx}',
    './components/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // Paleta Gloma — actualizada a la identidad de la landing (Sprint 21
        // #290): Deep Forest #004D40, Algorithmic Mint #4DB6AC, Soft Mint
        // #E0F2F1, Technical Black #101817.
        //
        // Los nombres de los tokens (`brown`, `rose`, `cream`) se conservan a
        // propósito: están usados ~800 veces en la app con un rol semántico
        // fijo — `brown` = primario oscuro (sidebar, títulos, botones),
        // `rose` = acento claro sobre oscuro, `rose-soft`/`cream` = fondos
        // claros. Cambiar los valores aquí retiñe toda la plataforma sin
        // tocar cada pantalla ni arriesgar contrastes.
        gloma: {
          brown: '#004D40',      // Deep Forest (primario)
          'brown-dark': '#003A30',
          'brown-darker': '#00271F',
          'brown-light': '#4A7A72',   // texto secundario (4.9:1 sobre blanco)
          rose: '#8FD6CE',       // mint claro (acento sobre fondo oscuro)
          'rose-soft': '#E0F2F1',     // Soft Mint (fondos y bordes suaves)
          cream: '#F5FAF9',      // fondo claro de la app
          // Tokens nuevos, por nombre real, para lo que se diseñe de ahora
          // en adelante:
          forest: '#004D40',
          mint: '#4DB6AC',       // Algorithmic Mint (CTAs y métricas)
          'soft-mint': '#E0F2F1',
          black: '#101817',      // Technical Black (fondos oscuros)
          // Superficie oscura de las páginas públicas (Sprint 32, `/demo`).
          // Son los mismos valores del objeto `BRAND` de `pages/gloma.tsx`,
          // ahora como tokens para no repetir hex sueltos. Contrastes sobre
          // `ink`: `ink-text` ≈ 15:1, `ink-muted` ≈ 7:1, `ink-err` ≈ 8:1.
          ink: '#101817',
          'ink-alt': '#0B1413',      // fondo del chat y de los inputs
          'ink-surface': '#1A2725',  // burbuja entrante, cuadro de texto
          'ink-text': '#E6EFEE',     // texto principal sobre oscuro
          'ink-muted': '#A3AFAD',    // texto secundario sobre oscuro
          'ink-err': '#FF9A8F',      // error sobre oscuro (siempre con ícono)
        },
      },
      fontFamily: {
        heading: ['Syne', 'system-ui', 'sans-serif'],
        body: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
