import React from "react"
import type { Metadata, Viewport } from 'next'
import { Inter, JetBrains_Mono } from 'next/font/google'
import { Toaster } from "sonner"

import './globals.css'
import { AuthProvider } from '../lib/auth-context'
import { AmbientBackground } from './components/AmbientBackground'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains-mono',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'Evalia — Multi-Agent Interview Evaluation System',
  description: 'Five specialized AI agents evaluate candidates through resume screening, technical interviews, behavioral assessment, and an isolated committee decision. Transparent, auditable, bias-reduced hiring.',
  keywords: ['AI interview', 'hiring evaluation', 'multi-agent', 'resume screening', 'CrewAI', 'Gemini AI'],
  authors: [{ name: 'Evalia' }],
  openGraph: {
    title: 'Evalia — Multi-Agent Interview Evaluation System',
    description: 'AI-powered candidate evaluation with 5 specialized agents and transparent, auditable decisions.',
    type: 'website',
  },
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#070810',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body>
        <AmbientBackground />
        <AuthProvider>{children}</AuthProvider>
        <Toaster
          position="bottom-right"
          richColors
          closeButton
          theme="dark"
          toastOptions={{
            style: {
              background: "rgba(17,18,30,0.92)",
              border: "1px solid rgba(255,255,255,0.08)",
              color: "#f9fafb",
              backdropFilter: "blur(16px)",
            },
          }}
        />
      </body>
    </html>
  )
}
