// REGISTRO ÚNICO de iconos del Hub. Los SVG se hornean EN BUILD (unplugin-icons, set Iconify
// `ion:` desde @iconify-json/ion) — offline, CSP-safe, tree-shaken, cero runtime/red.
// Para AÑADIR un icono: una línea `import x from "~icons/ion/<name>?raw"` + su entrada en SVGS.
// Cualquier set Iconify vale (lucide/mdi/tabler…); aquí solo `ion:` porque es lo que usa el Hub.
//
// De aquí salen los DOS caminos por los que se pinta un icono, para que no se desincronicen:
//   · `resolveIcon()`  → `<ion-icon :icon>`  — el shell (Vue), vía <HubIcon>.
//   · `iconRegistry()` → `<ion-icon name="…">` — los ok-* de OutfitKit y los WC de los módulos,
//     volcado en `addIcons()` desde main.ts. Ojo: ionicons SANEA el nombre a `[a-z0-9-]`, así que
//     un nombre con prefijo de colección (`mdi:home`) NO vale en `name=` — va por `:icon`.
// `icons.test.ts` escanea shell + OutfitKit + módulos y falla si algún nombre usado no está aquí.
//
// Los iconos que declara un MÓDULO en su manifest (`icon`/`navigation[].icon`) no hace falta
// añadirlos: `module-toolkit pack` hornea su SVG en el manifest construido (ADR option-b) y
// `resolveIcon` lo pasa tal cual.
import { svgToIcon, isInlineSvg } from "./iconify";

import addOutline from "~icons/ion/add-outline?raw";
import businessOutline from "~icons/ion/business-outline?raw";
import cardOutline from "~icons/ion/card-outline?raw";
import cameraOutline from "~icons/ion/camera-outline?raw";
import checkmarkCircleOutline from "~icons/ion/checkmark-circle-outline?raw";
import cloudUploadOutline from "~icons/ion/cloud-upload-outline?raw";
import colorPaletteOutline from "~icons/ion/color-palette-outline?raw";
import cubeOutline from "~icons/ion/cube-outline?raw";
import documentTextOutline from "~icons/ion/document-text-outline?raw";
import downloadOutline from "~icons/ion/download-outline?raw";
import ellipse from "~icons/ion/ellipse?raw";
import removeOutline from "~icons/ion/remove-outline?raw";
import extensionPuzzleOutline from "~icons/ion/extension-puzzle-outline?raw";
import globeOutline from "~icons/ion/globe-outline?raw";
import gridOutline from "~icons/ion/grid-outline?raw";
import hardwareChipOutline from "~icons/ion/hardware-chip-outline?raw";
import imageOutline from "~icons/ion/image-outline?raw";
import informationCircleOutline from "~icons/ion/information-circle-outline?raw";
import keypadOutline from "~icons/ion/keypad-outline?raw";
import languageOutline from "~icons/ion/language-outline?raw";
import logInOutline from "~icons/ion/log-in-outline?raw";
import logOutOutline from "~icons/ion/log-out-outline?raw";
import mailOutline from "~icons/ion/mail-outline?raw";
import peopleOutline from "~icons/ion/people-outline?raw";
import personCircleOutline from "~icons/ion/person-circle-outline?raw";
import phonePortraitOutline from "~icons/ion/phone-portrait-outline?raw";
import pulseOutline from "~icons/ion/pulse-outline?raw";
import readerOutline from "~icons/ion/reader-outline?raw";
import receiptOutline from "~icons/ion/receipt-outline?raw";
import rocketOutline from "~icons/ion/rocket-outline?raw";
import refreshOutline from "~icons/ion/refresh-outline?raw";
import saveOutline from "~icons/ion/save-outline?raw";
import serverOutline from "~icons/ion/server-outline?raw";
import shieldCheckmarkOutline from "~icons/ion/shield-checkmark-outline?raw";
import speedometerOutline from "~icons/ion/speedometer-outline?raw";
import storefrontOutline from "~icons/ion/storefront-outline?raw";
import tabletPortraitOutline from "~icons/ion/tablet-portrait-outline?raw";
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
import closeOutline from "~icons/ion/close-outline?raw";
import stopCircleOutline from "~icons/ion/stop-circle-outline?raw";
import copyOutline from "~icons/ion/copy-outline?raw";
import codeSlashOutline from "~icons/ion/code-slash-outline?raw";
// Logos de marca de SO — los botones "Descargar Bridge" (SystemPage) pintan uno por sistema,
// en paridad con los de erplora.com/download/. `logo-tux` es el pingüino de Linux.
import logoWindows from "~icons/ion/logo-windows?raw";
import logoTux from "~icons/ion/logo-tux?raw";
import logoAndroid from "~icons/ion/logo-android?raw";
// «Continuar con Google» del login (ADR-0157 §8).
import logoGoogle from "~icons/ion/logo-google?raw";

// Iconos que se pintan POR NOMBRE (`<ion-icon name="…">`) desde los ok-* de OutfitKit y desde los
// Web Components de los módulos. Antes vivían en un `addIcons()` aparte, en main.ts, importados de
// `ionicons/icons`: ese segundo registro se desincronizaba de este y el icono que faltaba en uno
// salía VACÍO. Ahora hay uno solo, y `src/lib/icons.test.ts` verifica que no falte ninguno.
import add from "~icons/ion/add?raw";
import alertCircleOutline from "~icons/ion/alert-circle-outline?raw";
import helpCircleOutline from "~icons/ion/help-circle-outline?raw";
import arrowForwardCircleOutline from "~icons/ion/arrow-forward-circle-outline?raw";
import appsOutline from "~icons/ion/apps-outline?raw";
import archiveOutline from "~icons/ion/archive-outline?raw";
import arrowRedoOutline from "~icons/ion/arrow-redo-outline?raw";
import arrowUndoOutline from "~icons/ion/arrow-undo-outline?raw";
import backspaceOutline from "~icons/ion/backspace-outline?raw";
import checkmarkOutline from "~icons/ion/checkmark-outline?raw";
import chevronDownOutline from "~icons/ion/chevron-down-outline?raw";
import chevronExpandOutline from "~icons/ion/chevron-expand-outline?raw";
import close from "~icons/ion/close?raw";
import cloudDownloadOutline from "~icons/ion/cloud-download-outline?raw";
import cloudOfflineOutline from "~icons/ion/cloud-offline-outline?raw";
import attachOutline from "~icons/ion/attach-outline?raw";
import contractOutline from "~icons/ion/contract-outline?raw";
import createOutline from "~icons/ion/create-outline?raw";
import documentAttachOutline from "~icons/ion/document-attach-outline?raw";
import documentOutline from "~icons/ion/document-outline?raw";
import ellipsisVertical from "~icons/ion/ellipsis-vertical?raw";
import expandOutline from "~icons/ion/expand-outline?raw";
import fileTrayOutline from "~icons/ion/file-tray-outline?raw";
import fileTrayStackedOutline from "~icons/ion/file-tray-stacked-outline?raw";
import folderOpenOutline from "~icons/ion/folder-open-outline?raw";
import funnelOutline from "~icons/ion/funnel-outline?raw";
import gift from "~icons/ion/gift?raw";
import giftOutline from "~icons/ion/gift-outline?raw";
import listOutline from "~icons/ion/list-outline?raw";
import mailOpenOutline from "~icons/ion/mail-open-outline?raw";
import menuOutline from "~icons/ion/menu-outline?raw";
import notificationsOffOutline from "~icons/ion/notifications-off-outline?raw";
import openOutline from "~icons/ion/open-outline?raw";
import pause from "~icons/ion/pause?raw";
import pencil from "~icons/ion/pencil?raw";
import play from "~icons/ion/play?raw";
import playOutline from "~icons/ion/play-outline?raw";
import powerOutline from "~icons/ion/power-outline?raw";
import printOutline from "~icons/ion/print-outline?raw";
import remove from "~icons/ion/remove?raw";
import ribbonOutline from "~icons/ion/ribbon-outline?raw";
import searchOutline from "~icons/ion/search-outline?raw";
import star from "~icons/ion/star?raw";
import swapVerticalOutline from "~icons/ion/swap-vertical-outline?raw";
import terminalOutline from "~icons/ion/terminal-outline?raw";
import trash from "~icons/ion/trash?raw";
import trashOutline from "~icons/ion/trash-outline?raw";
import trendingDown from "~icons/ion/trending-down?raw";
import trendingUp from "~icons/ion/trending-up?raw";

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
  "camera-outline": cameraOutline,
  "checkmark-circle-outline": checkmarkCircleOutline,
  "cloud-upload-outline": cloudUploadOutline,
  "color-palette-outline": colorPaletteOutline,
  "cube-outline": cubeOutline,
  "document-text-outline": documentTextOutline,
  "download-outline": downloadOutline,
  "ellipse": ellipse,
  "remove-outline": removeOutline,
  "extension-puzzle-outline": extensionPuzzleOutline,
  "globe-outline": globeOutline,
  "grid-outline": gridOutline,
  "hardware-chip-outline": hardwareChipOutline,
  "image-outline": imageOutline,
  "information-circle-outline": informationCircleOutline,
  "keypad-outline": keypadOutline,
  "language-outline": languageOutline,
  "log-in-outline": logInOutline,
  "log-out-outline": logOutOutline,
  "mail-outline": mailOutline,
  "people-outline": peopleOutline,
  "person-circle-outline": personCircleOutline,
  "phone-portrait-outline": phonePortraitOutline,
  "pulse-outline": pulseOutline,
  "reader-outline": readerOutline,
  "receipt-outline": receiptOutline,
  "rocket-outline": rocketOutline,
  "refresh-outline": refreshOutline,
  "save-outline": saveOutline,
  "server-outline": serverOutline,
  "shield-checkmark-outline": shieldCheckmarkOutline,
  "speedometer-outline": speedometerOutline,
  "storefront-outline": storefrontOutline,
  "tablet-portrait-outline": tabletPortraitOutline,
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
  "close-outline": closeOutline,
  "stop-circle-outline": stopCircleOutline,
  "copy-outline": copyOutline,
  "code-slash-outline": codeSlashOutline,
  "logo-windows": logoWindows,
  "logo-tux": logoTux,
  "logo-android": logoAndroid,
  "logo-google": logoGoogle,
  "panel-left": panelLeft,

  // Pintados por nombre desde los ok-* (OutfitKit) y los WC de los módulos — ver el bloque de
  // imports de arriba.
  add,
  "alert-circle-outline": alertCircleOutline,
  // «No lo hemos podido leer» (hub#375): la interrogación es la señal de que falta el DATO, no de
  // que el dato sea malo — un triángulo de alerta diría que algo va mal, que es justo lo que no
  // sabemos.
  "help-circle-outline": helpCircleOutline,
  "arrow-forward-circle-outline": arrowForwardCircleOutline,
  "apps-outline": appsOutline,
  "archive-outline": archiveOutline,
  "arrow-redo-outline": arrowRedoOutline,
  "arrow-undo-outline": arrowUndoOutline,
  "backspace-outline": backspaceOutline,
  "checkmark-outline": checkmarkOutline,
  "chevron-down-outline": chevronDownOutline,
  "chevron-expand-outline": chevronExpandOutline,
  close,
  "cloud-download-outline": cloudDownloadOutline,
  "cloud-offline-outline": cloudOfflineOutline,
  "attach-outline": attachOutline,
  "contract-outline": contractOutline,
  "create-outline": createOutline,
  "document-attach-outline": documentAttachOutline,
  "document-outline": documentOutline,
  "ellipsis-vertical": ellipsisVertical,
  "expand-outline": expandOutline,
  "file-tray-outline": fileTrayOutline,
  "file-tray-stacked-outline": fileTrayStackedOutline,
  "folder-open-outline": folderOpenOutline,
  "funnel-outline": funnelOutline,
  gift,
  "gift-outline": giftOutline,
  "list-outline": listOutline,
  "mail-open-outline": mailOpenOutline,
  "menu-outline": menuOutline,
  "notifications-off-outline": notificationsOffOutline,
  "open-outline": openOutline,
  pause,
  pencil,
  play,
  "play-outline": playOutline,
  "power-outline": powerOutline,
  "print-outline": printOutline,
  remove,
  "ribbon-outline": ribbonOutline,
  "search-outline": searchOutline,
  star,
  "swap-vertical-outline": swapVerticalOutline,
  "terminal-outline": terminalOutline,
  trash,
  "trash-outline": trashOutline,
  "trending-down": trendingDown,
  "trending-up": trendingUp,
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

/**
 * El registro entero como `nombre → data-URI`, para volcarlo en `addIcons()` (ionicons) al arrancar.
 *
 * Hay dos formas de pintar un icono y las dos tienen que beber de ESTE mapa:
 * - `<ion-icon :icon="…">` — el shell (Vue) vía `<HubIcon>` → `resolveIcon()`.
 * - `<ion-icon name="…">` — los ok-* de OutfitKit y los WC de los módulos, que son Web Components
 *   ajenos y no pueden llamar a `resolveIcon()`. `ion-icon` resuelve el nombre contra el mapa
 *   global `window.Ionicons.map`, que es justo lo que `addIcons()` rellena; si un nombre no está,
 *   ionicons intenta bajar el SVG por red y en offline/CSP el icono sale VACÍO y sin error.
 *
 * Alimentar ambos caminos desde el mismo sitio es lo que evita que se desincronicen. Usamos solo la
 * API pública de ionicons (`addIcons`), sin tocar el Web Component: una subida de versión de Ionic
 * no rompe esto.
 */
export function iconRegistry(): Record<string, string> {
  const registry: Record<string, string> = {};
  for (const [name, svg] of Object.entries(SVGS)) registry[name] = svgToIcon(svg);
  for (const [alias, target] of Object.entries(ALIASES)) {
    const svg = SVGS[target];
    if (svg) registry[alias] = svgToIcon(svg);
  }
  return registry;
}

/**
 * Los iconos que TRAE UN MÓDULO (su sidecar `dist/icons.json`, nombre → SVG inline, horneado por
 * `module-toolkit build`), en formato `addIcons()`.
 *
 * El shell NO puede conocer los iconos de un módulo — menos aún los de uno de terceros instalado
 * desde el marketplace. Así que el módulo los trae dentro del zip y el shell los registra al
 * cargarlo (module-loader). Es lo que hace que un módulo sea autónomo: añadir uno nuevo no obliga a
 * tocar este fichero ni a redesplegar el Hub.
 */
export function moduleIconRegistry(icons: Record<string, string>): Record<string, string> {
  const registry: Record<string, string> = {};
  for (const [name, svg] of Object.entries(icons)) {
    // Lo que el shell ya trae no se re-registra: es el mismo dibujo pero no el mismo string (el
    // shell lo hornea con unplugin-icons y el módulo con @iconify/utils), y ionicons escupiría un
    // "Multiple icons were mapped to name …" por cada uno. Gana el del shell; el módulo aporta
    // lo que falta, que es justo lo que lo hace autónomo.
    if (name in SVGS) continue;
    if (isInlineSvg(svg)) registry[name] = svgToIcon(svg);
  }
  return registry;
}
