import type { CapacitorConfig } from "@capacitor/cli";

const PROD_URL = process.env.JAI_PWA_URL || "https://jai.yourdomain.com";

const config: CapacitorConfig = {
  appId: "ai.jai.app",
  appName: "JAI",
  // Two distribution modes:
  //   - hosted PWA (server.url):    iOS WebView loads our live PWA. Easy updates,
  //                                  no need to re-submit for content changes.
  //   - bundled offline (webDir):   ship the static export in the .ipa.
  // We default to hosted; flip by removing server.url and setting webDir below.
  server: {
    url: PROD_URL,
    cleartext: false,
  },
  webDir: "../web/.next/static",   // unused while server.url is set
  ios: {
    contentInset: "always",
    scheme: "JAI",
    backgroundColor: "#0b0b0c",
    limitsNavigationsToAppBoundDomains: true,
    handleApplicationNotifications: true,
  },
  android: {
    backgroundColor: "#0b0b0c",
  },
  plugins: {
    PushNotifications: {
      presentationOptions: ["badge", "sound", "alert"],
    },
    StatusBar: {
      style: "DARK",
      backgroundColor: "#0b0b0c",
      overlaysWebView: true,
    },
    Keyboard: {
      resize: "body",
      style: "DARK",
      resizeOnFullScreen: true,
    },
  },
};

export default config;
