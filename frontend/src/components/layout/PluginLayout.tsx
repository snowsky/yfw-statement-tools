import React from 'react'

interface Props {
  children: React.ReactNode
}

export default function PluginLayout({ children }: Props) {
  return (
    <div style={{ minHeight: '100vh', background: '#f9fafb' }}>
      {children}
    </div>
  )
}
