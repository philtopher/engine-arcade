/** @type {import('tailwindcss').Config} */
module.exports = {
  prefix: 'tw-',  // All Tailwind classes will be prefixed with tw-
  content: [
    "./templates/**/*.html",
    "./static/src/**/*.js"
  ],
  theme: {
    extend: {},
  },
  plugins: [],
} 