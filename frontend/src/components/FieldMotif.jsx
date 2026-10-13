import React from 'react'

/**
 * A subtle, original agricultural motif -- rolling fields with crop rows
 * under a rising sun, drawn as flat geometric shapes in CropRetain's own
 * palette. Not derived from any external image or stock asset (avoids any
 * licensing question), and deliberately abstract rather than
 * photographic so it reads as premium product chrome, not decoration --
 * "support the interface", per the brief, not a photo gallery.
 *
 * Meant to sit as a low-opacity background layer (see usage in
 * SellingJourney's dark hero), never as a standalone image -- CropRetain
 * stays data-first.
 */
export default function FieldMotif({ className = '' }) {
  return (
    <svg
      viewBox="0 0 400 160"
      preserveAspectRatio="xMidYMax slice"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      {/* sun */}
      <circle cx="330" cy="40" r="26" fill="currentColor" opacity="0.10" />
      {/* far hill */}
      <path d="M0,110 Q100,80 220,100 T400,90 V160 H0 Z" fill="currentColor" opacity="0.06" />
      {/* near hill */}
      <path d="M0,130 Q120,105 240,125 T400,115 V160 H0 Z" fill="currentColor" opacity="0.10" />
      {/* crop rows */}
      {Array.from({ length: 9 }).map((_, i) => (
        <path
          key={i}
          d={`M${-20 + i * 55},160 Q${10 + i * 55},128 ${40 + i * 55},160`}
          stroke="currentColor"
          strokeWidth="2"
          fill="none"
          opacity="0.14"
        />
      ))}
    </svg>
  )
}
