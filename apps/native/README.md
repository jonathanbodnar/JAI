# JAI native (Capacitor)

This wraps the deployed PWA in an iOS (and optionally Android) native shell so
you can ship JAI to the App Store, get a real icon on the home screen, push
notifications, haptics, and full mic permissions without Safari quirks.

## Architecture

`capacitor.config.ts` uses `server.url` to point the native WebView at the live
PWA. That means every code push to Cloudflare Pages reaches users immediately
— no resubmission needed for content changes. (Set `webDir` and remove
`server.url` if Apple ever asks for a "real" bundled app.)

## First-time setup (one-time, on macOS with Xcode 16+)

```bash
cd apps/native
pnpm install

# 1. Set the PWA URL the WebView will load
export JAI_PWA_URL=https://jai.yourdomain.com

# 2. Generate the native iOS project
pnpm init:ios

# 3. Open Xcode
pnpm open:ios
```

In Xcode:

1. Select the `App` target → Signing & Capabilities → set your Team and a
   unique Bundle Identifier (e.g. `ai.jai.app`).
2. Capabilities → add:
   - **Push Notifications** (for nightly reflection alerts)
   - **Background Modes** → Audio (so push-to-talk works when the screen dims)
   - **App Groups** (only if you ever want a widget)
3. Set the launch screen + app icon (drag `apps/web/public/icon-1024.png`).

## Build & ship

```bash
# Sync any plugin/web changes into the iOS project
pnpm sync

# Archive
pnpm open:ios          # Product → Archive → Distribute App → App Store Connect
```

## Push notifications (nightly reflection)

The backend can POST to APNs via the consolidation job. To wire:

1. In Apple Developer → Keys, create an APNs key (.p8). Save the key id +
   team id.
2. In Supabase (or your KMS), store `APNS_KEY`, `APNS_KEY_ID`, `APNS_TEAM_ID`,
   `APNS_BUNDLE_ID`.
3. In `apps/api/src/jai_api/jobs/consolidate.py`, after the reflection message
   is created, send an APNs push containing the first sentence.
4. The Capacitor app handles the push via `PushNotifications` plugin and routes
   the user to `/` on tap.

(That wiring is intentionally not in v0.7 — it requires real APNs creds. See
the roadmap.)

## Android

```bash
pnpm init:android
pnpm open:android      # opens Android Studio
```

Same idea, just with Android Studio + a Google Play account.
