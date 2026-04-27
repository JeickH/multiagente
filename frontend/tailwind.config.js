module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx}',
    './components/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // Paleta Gloma — brief identidad_gloma
        gloma: {
          brown: '#5E503F',      // marrón tierra (primario)
          'brown-dark': '#4A4032',
          'brown-darker': '#3A3128',
          'brown-light': '#8B7A67',
          rose: '#F7D1CD',       // rosa empolvado (acento)
          'rose-soft': '#FBE9E7',
          cream: '#FDFBF7',      // fondo claro
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
