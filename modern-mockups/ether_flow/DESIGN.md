# Design System Specification: The Precision Canvas

## 1. Overview & Creative North Star
This design system is built upon the "Creative North Star" of **The Precision Canvas**. In the realm of file management, software often feels like a rigid, industrial tool. We are shifting that paradigm toward a high-end editorial experience. 

The system prioritizes intentional asymmetry, breathing room (whitespace), and tonal depth over traditional borders and boxes. By utilizing a sophisticated palette of grays and whites paired with a high-energy "vibrant blue," we create a workspace that feels less like a filing cabinet and more like a curated digital atelier.

## 2. Colors & Surface Philosophy
The palette is rooted in Material Design conventions but applied with an editorial eye for subtlety.

### Surface Hierarchy & Nesting
Instead of a flat grid, this design system treats the UI as a series of nested layers.
- **Base Layer:** Use `surface` (`#f7f9fb`) for the application background.
- **Navigation Pane:** Use `surface-container-low` (`#f2f4f6`) to subtly distinguish the side-by-side pane from the content area.
- **Active Content Area:** Use `surface-container-lowest` (`#ffffff`) for the primary workspace to give it a "raised" and focused feel.
- **Overlays/Modals:** Use `surface-bright` with a backdrop-blur (12px-20px) to create a premium "Glassmorphism" effect.

### The "No-Line" Rule
**Explicit Instruction:** Do not use 1px solid borders to define sections or sidebars. Boundaries must be defined solely through background color shifts or the spacing scale. For example, the side navigation pane sits on `surface-container-low` and terminates where the `surface-container-lowest` content area begins. This creates a soft, organic transition that feels more modern than a hard line.

### Signature Textures
For primary CTAs like the "Open" button, move beyond flat fills. Use a subtle linear gradient transitioning from `primary` (`#0058bc`) to `primary_container` (`#0070eb`) at a 135-degree angle. This provides a "jewel-toned" depth that feels high-end and intentional.

## 3. Typography
The system employs a dual-font strategy to balance character with utility.

*   **Display & Headlines (Manrope):** Use Manrope for `display-lg` through `headline-sm`. Its geometric yet warm curves provide the "editorial" voice of the system. 
*   **Interface & Utility (Inter):** Use Inter for `title-lg` through `label-sm`. Inter’s high x-height and neutral character make it the perfect "functional" partner for file names, paths, and metadata.

**Hierarchy Note:** Maintain high contrast between sizes. A `headline-lg` (2rem) folder title should feel significantly more authoritative than a `body-md` (0.875rem) file description to guide the eye through the layout.

## 4. Elevation & Depth
Depth is achieved through **Tonal Layering** and **Ambient Shadows** rather than structural lines.

- **The Layering Principle:** Stack `surface-container` tiers to create hierarchy. A card or file item should never have a border; instead, place a `surface-container-lowest` card on a `surface-container` background.
- **Ambient Shadows:** When an element must "float" (e.g., a context menu), use a shadow with a blur value of `24px` and an opacity of `4%-6%`. The shadow color should be a tinted version of `on_surface` (`#191c1e`) to mimic natural, soft lighting.
- **The "Ghost Border" Fallback:** If accessibility requirements demand a border, use the "Ghost Border" technique: `outline_variant` (`#c1c6d7`) at 15% opacity. Never use 100% opaque borders.

## 5. Components

### Buttons
*   **Primary (Action):** Roundedness `DEFAULT` (0.5rem). Background: Primary Gradient. Label: `label-md` in `on_primary` (`#ffffff`).
*   **Secondary (Ghost):** No background or border. Use `secondary` (`#505f76`) for text. On hover, apply a `surface-container-high` background shift.

### Navigation Panes (The Pane Structure)
The side-by-side structure should feel architectural.
*   **Left Pane (Navigation):** `surface-container-low`. No divider line. Use `8px` (Spacing `2`) horizontal padding for items.
*   **Active State:** The selected folder in the navigation should use a `secondary_container` (`#d0e1fb`) background with a rounded corner of `DEFAULT` (0.5rem).

### Lists & Folders
*   **The "No-Divider" Rule:** Forbid horizontal lines between file rows. Separate items using `12` (3rem) or `16` (4rem) height containers and distinguish them with a very subtle `surface-container-highest` hover state.
*   **File Icons:** Use monochromatic icons in `secondary` or `outline` colors to keep the focus on the vibrant blue primary actions.

### Tooltips & Chips
*   **Tooltips:** Use `inverse_surface` (`#2d3133`) with `inverse_on_surface` (`#eff1f3`) text. 
*   **Selection Chips:** Rounded `full` (9999px). Use `primary_fixed` (`#d8e2ff`) for the background to provide a soft "glow" of the brand color without the weight of the primary button.

## 6. Do's and Don'ts

### Do
*   **Do** use the Spacing Scale (specifically `4`, `6`, and `8`) to create "visual silences" between disparate groups of information.
*   **Do** use `0.5rem` (8px) for standard components and `1rem` (16px) for large container groupings to create a hierarchical "softness."
*   **Do** use `on_surface_variant` (`#414755`) for secondary metadata to ensure it doesn't compete with primary file names.

### Don'ts
*   **Don't** use pure black (`#000000`) for text or shadows. Use `on_surface` to maintain the "soft gray" aesthetic.
*   **Don't** use 1px dividers. If you feel the need to separate two sections, increase the spacing or change the `surface-container` tier.
*   **Don't** use high-saturation colors for anything other than the primary action. The "modern/professional" feel relies on the restraint of the gray/white palette.