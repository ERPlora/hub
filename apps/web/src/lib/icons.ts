// Registro de iconos del shell del Hub. Los SVG se hornean EN BUILD (unplugin-icons, set
// Iconify `ion:` desde @iconify-json/ion) — offline, CSP-safe, tree-shaken, cero runtime/red.
// Para AÑADIR un icono del shell: una línea `import x from "~icons/ion/<name>?raw"` + su entrada.
// Cualquier set Iconify vale (lucide/mdi/tabler…); aquí solo `ion:` porque es lo que usa el shell.
//
// Los iconos que declara un MÓDULO (module.json `icon`/`navigation[].icon`) NO viven aquí: el
// `module-toolkit pack` hornea su SVG en el manifest construido (ADR option-b) y `resolveIcon`
// lo pasa tal cual. Este registro es solo el set propio del shell + fallback.
import { svgToIcon, isInlineSvg } from "./iconify";

import addOutline from "~icons/ion/add-outline?raw";
import businessOutline from "~icons/ion/business-outline?raw";
import cardOutline from "~icons/ion/card-outline?raw";
import checkmarkCircleOutline from "~icons/ion/checkmark-circle-outline?raw";
import cloudUploadOutline from "~icons/ion/cloud-upload-outline?raw";
import colorPaletteOutline from "~icons/ion/color-palette-outline?raw";
import cubeOutline from "~icons/ion/cube-outline?raw";
import documentTextOutline from "~icons/ion/document-text-outline?raw";
import downloadOutline from "~icons/ion/download-outline?raw";
import ellipse from "~icons/ion/ellipse?raw";
import extensionPuzzleOutline from "~icons/ion/extension-puzzle-outline?raw";
import globeOutline from "~icons/ion/globe-outline?raw";
import gridOutline from "~icons/ion/grid-outline?raw";
import hardwareChipOutline from "~icons/ion/hardware-chip-outline?raw";
import informationCircleOutline from "~icons/ion/information-circle-outline?raw";
import keypadOutline from "~icons/ion/keypad-outline?raw";
import languageOutline from "~icons/ion/language-outline?raw";
import logInOutline from "~icons/ion/log-in-outline?raw";
import logOutOutline from "~icons/ion/log-out-outline?raw";
import mailOutline from "~icons/ion/mail-outline?raw";
import peopleOutline from "~icons/ion/people-outline?raw";
import personCircleOutline from "~icons/ion/person-circle-outline?raw";
import pulseOutline from "~icons/ion/pulse-outline?raw";
import readerOutline from "~icons/ion/reader-outline?raw";
import receiptOutline from "~icons/ion/receipt-outline?raw";
import refreshOutline from "~icons/ion/refresh-outline?raw";
import saveOutline from "~icons/ion/save-outline?raw";
import serverOutline from "~icons/ion/server-outline?raw";
import shieldCheckmarkOutline from "~icons/ion/shield-checkmark-outline?raw";
import speedometerOutline from "~icons/ion/speedometer-outline?raw";
import storefrontOutline from "~icons/ion/storefront-outline?raw";
import ticketOutline from "~icons/ion/ticket-outline?raw";
import trendingDownOutline from "~icons/ion/trending-down-outline?raw";
import trendingUpOutline from "~icons/ion/trending-up-outline?raw";
import walletOutline from "~icons/ion/wallet-outline?raw";
import homeOutline from "~icons/ion/home-outline?raw";
import settingsOutline from "~icons/ion/settings-outline?raw";
import chevronForward from "~icons/ion/chevron-forward?raw";
import chevronBack from "~icons/ion/chevron-back?raw";
import chevronForwardOutline from "~icons/ion/chevron-forward-outline?raw";
import chevronBackOutline from "~icons/ion/chevron-back-outline?raw";
import warningOutline from "~icons/ion/warning-outline?raw";
import bagCheckOutline from "~icons/ion/bag-check-outline?raw";
import bookmark from "~icons/ion/bookmark?raw";
import briefcase from "~icons/ion/briefcase?raw";
import calendarOutline from "~icons/ion/calendar-outline?raw";
import card from "~icons/ion/card?raw";
import chatbubblesOutline from "~icons/ion/chatbubbles-outline?raw";
import checkboxOutline from "~icons/ion/checkbox-outline?raw";
import clipboardOutline from "~icons/ion/clipboard-outline?raw";
import cube from "~icons/ion/cube?raw";
import flameOutline from "~icons/ion/flame-outline?raw";
import folderOutline from "~icons/ion/folder-outline?raw";
import funnel from "~icons/ion/funnel?raw";
import headsetOutline from "~icons/ion/headset-outline?raw";
import layersOutline from "~icons/ion/layers-outline?raw";
import mapOutline from "~icons/ion/map-outline?raw";
import pricetag from "~icons/ion/pricetag?raw";
import pricetags from "~icons/ion/pricetags?raw";
import print from "~icons/ion/print?raw";
import send from "~icons/ion/send?raw";
import settings from "~icons/ion/settings?raw";
import shieldOutline from "~icons/ion/shield-outline?raw";
import starOutline from "~icons/ion/star-outline?raw";
import statsChart from "~icons/ion/stats-chart?raw";
import storefront from "~icons/ion/storefront?raw";
import timeOutline from "~icons/ion/time-outline?raw";
import timerOutline from "~icons/ion/timer-outline?raw";
import tv from "~icons/ion/tv?raw";
import cashOutline from "~icons/ion/cash-outline?raw";
import cartOutline from "~icons/ion/cart-outline?raw";
import cart from "~icons/ion/cart?raw";
import sparklesOutline from "~icons/ion/sparkles-outline?raw";
import notificationsOutline from "~icons/ion/notifications-outline?raw";
import arrowBackOutline from "~icons/ion/arrow-back-outline?raw";
import sunnyOutline from "~icons/ion/sunny-outline?raw";
import moonOutline from "~icons/ion/moon-outline?raw";
import contrastOutline from "~icons/ion/contrast-outline?raw";
import personOutline from "~icons/ion/person-outline?raw";
import bugOutline from "~icons/ion/bug-outline?raw";
import closeOutline from "~icons/ion/close-outline?raw";
import stopCircleOutline from "~icons/ion/stop-circle-outline?raw";

// `panel-left` (lucide) — NO hay equivalente en el set `ion:`; se hornea a mano para dar paridad
// exacta con el rail-toggle de Cloud (que usa `lucide:panel-left`). SVG inline = offline/CSP-safe,
// igual que los `?raw` de arriba (resolveIcon lo trata como SVG ya resuelto).
const panelLeft =
  '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/></g></svg>';

/** SVG inline (string) por nombre Iconify `ion:`. Build-time, no runtime. */
const SVGS: Record<string, string> = {
  "add-outline": addOutline,
  "business-outline": businessOutline,
  "card-outline": cardOutline,
  "checkmark-circle-outline": checkmarkCircleOutline,
  "cloud-upload-outline": cloudUploadOutline,
  "color-palette-outline": colorPaletteOutline,
  "cube-outline": cubeOutline,
  "document-text-outline": documentTextOutline,
  "download-outline": downloadOutline,
  "ellipse": ellipse,
  "extension-puzzle-outline": extensionPuzzleOutline,
  "globe-outline": globeOutline,
  "grid-outline": gridOutline,
  "hardware-chip-outline": hardwareChipOutline,
  "information-circle-outline": informationCircleOutline,
  "keypad-outline": keypadOutline,
  "language-outline": languageOutline,
  "log-in-outline": logInOutline,
  "log-out-outline": logOutOutline,
  "mail-outline": mailOutline,
  "people-outline": peopleOutline,
  "person-circle-outline": personCircleOutline,
  "pulse-outline": pulseOutline,
  "reader-outline": readerOutline,
  "receipt-outline": receiptOutline,
  "refresh-outline": refreshOutline,
  "save-outline": saveOutline,
  "server-outline": serverOutline,
  "shield-checkmark-outline": shieldCheckmarkOutline,
  "speedometer-outline": speedometerOutline,
  "storefront-outline": storefrontOutline,
  "ticket-outline": ticketOutline,
  "trending-down-outline": trendingDownOutline,
  "trending-up-outline": trendingUpOutline,
  "wallet-outline": walletOutline,
  "home-outline": homeOutline,
  "settings-outline": settingsOutline,
  "chevron-forward": chevronForward,
  "chevron-back": chevronBack,
  "chevron-forward-outline": chevronForwardOutline,
  "chevron-back-outline": chevronBackOutline,
  "warning-outline": warningOutline,
  "bag-check-outline": bagCheckOutline,
  "bookmark": bookmark,
  "briefcase": briefcase,
  "calendar-outline": calendarOutline,
  "card": card,
  "chatbubbles-outline": chatbubblesOutline,
  "checkbox-outline": checkboxOutline,
  "clipboard-outline": clipboardOutline,
  "cube": cube,
  "flame-outline": flameOutline,
  "folder-outline": folderOutline,
  "funnel": funnel,
  "headset-outline": headsetOutline,
  "layers-outline": layersOutline,
  "map-outline": mapOutline,
  "pricetag": pricetag,
  "pricetags": pricetags,
  "print": print,
  "send": send,
  "settings": settings,
  "shield-outline": shieldOutline,
  "star-outline": starOutline,
  "stats-chart": statsChart,
  "storefront": storefront,
  "time-outline": timeOutline,
  "timer-outline": timerOutline,
  "tv": tv,
  "cash-outline": cashOutline,
  "cart-outline": cartOutline,
  "cart": cart,
  "sparkles-outline": sparklesOutline,
  "notifications-outline": notificationsOutline,
  "arrow-back-outline": arrowBackOutline,
  "sunny-outline": sunnyOutline,
  "moon-outline": moonOutline,
  "contrast-outline": contrastOutline,
  "person-outline": personOutline,
  "bug-outline": bugOutline,
  "close-outline": closeOutline,
  "stop-circle-outline": stopCircleOutline,
  "panel-left": panelLeft,
};

// Alias de nombres estilo lucide que arrastran manifests antiguos → equivalente `ion:`.
const ALIASES: Record<string, string> = {
  users: "people-outline",
  "dollar-sign": "cash-outline",
  "file-text": "document-text-outline",
  "shopping-cart": "cart-outline",
};

const FALLBACK = SVGS["cube-outline"];

/**
 * Nombre de icono (o SVG inline de un módulo) → data-URI para `<ion-icon :icon>`.
 * - SVG inline (`<svg…>`, módulo option-b) → se usa tal cual.
 * - Nombre Iconify `ion:` del set del shell (con alias lucide) → SVG horneado.
 * - Desconocido → `cube-outline`.
 */
export function resolveIcon(name?: string): string {
  if (!name) return svgToIcon(FALLBACK);
  if (isInlineSvg(name)) return svgToIcon(name);
  const alias = ALIASES[name];
  const svg = SVGS[name] ?? (alias ? SVGS[alias] : undefined);
  return svgToIcon(svg ?? FALLBACK);
}

/** Compat: los manifests de módulo declaran `navigation[].icon` por nombre. Alias de resolveIcon. */
export const manifestIcon = resolveIcon;
