# 🎨 ModelMesh Brand Assets

This directory contains official branding and visual assets for ModelMesh.

## Icons & Logos

### `favicon.svg`
**Size:** 32×32px | **Format:** SVG  
**Usage:** Browser tabs, favorites, app icons  
**Description:** Compact mesh network icon with directional routing arrow

### `icon.svg`
**Size:** 200×200px | **Format:** SVG  
**Usage:** Apple touch icons, app stores, high-res display  
**Description:** Detailed mesh network with connected nodes and central routing indicator

### `logo-light.svg`
**Size:** 200×200px | **Format:** SVG  
**Usage:** Light backgrounds, standalone logo  
**Description:** Circular mesh design with layered nodes and connections, optimized for light themes

### `badge.svg`
**Size:** 300×100px | **Format:** SVG  
**Usage:** README badges, documentation, social media  
**Description:** Horizontal badge with icon, name, and tagline

### `banner.svg`
**Size:** 1200×400px | **Format:** SVG  
**Usage:** README headers, social media, promotional materials  
**Description:** Full-featured banner with icon, branding, and feature highlights

## Design System

### Color Palette
- **Primary Green:** `#10b981` (Emerald 500)
- **Dark Green:** `#047857` (Emerald 700)
- **Teal Accent:** `#059669` (Emerald 600)
- **Background:** `#f0fdf4` (Emerald 50)

### Typography (Implementation)
- **Headlines:** Arial, Bold, 24-56px
- **Body:** Arial, Regular, 12-16px
- **Feature Tags:** Arial, Bold, 12px

### Visual Elements
- **Mesh Nodes:** Circular, varying sizes (2.5-8px)
- **Connection Lines:** 1.5-2.5px stroke width
- **Routing Arrow:** Directional indicator, 2.5px stroke
- **Border Radius:** 6-12px for containers
- **Opacity Layers:** 0.5-0.8 for visual hierarchy

## Integration Guide

### Next.js Layout
```typescript
export const metadata: Metadata = {
  icons: {
    icon: '/favicon.svg',
    apple: '/icon.svg',
  },
  openGraph: {
    images: [{ url: '/banner.svg' }],
  },
}
```

### HTML Head
```html
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/icon.svg">
```

### Markdown README
```markdown
![ModelMesh](/frontend/public/badge.svg)
```

## Usage Rights

These assets are part of the ModelMesh project and should be used in accordance with the project's LICENSE file.

---

**Asset Location:** `frontend/public/`  
**Last Updated:** 2026-03-28  
**Maintained By:** ModelMesh Team
