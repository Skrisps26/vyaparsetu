import '@fontsource/noto-sans-malayalam/400.css'
import '@fontsource/noto-sans-malayalam/500.css'
import '@fontsource/noto-sans-malayalam/700.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ThemeProvider } from 'next-themes'
import App from './App'
import './index.css'

createRoot(document.getElementById('root')!).render(<StrictMode><ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}><App /></ThemeProvider></StrictMode>)
