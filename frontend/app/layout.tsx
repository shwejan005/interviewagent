import React from "react"
import type { Metadata, Viewport } from 'next'
import { Inter, JetBrains_Mono } from 'next/font/google'

import './globals.css'
import { AuthProvider } from '../lib/auth-context'

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
  themeColor: '#05080f',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body
        style={{
          fontFamily: 'var(--font-inter, var(--font-sans))',
          minHeight: '100vh',
        }}
      >
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  )
}
