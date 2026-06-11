// Resolución de iconos de manifest (module.json `navigation[].icon`) → SVG de ionicons.
// Los manifests declaran iconos POR NOMBRE ('cube', 'stats-chart'…); en @ionic/vue los
// ion-icon no auto-resuelven nombres (no hay loader CDN), así que el shell mapea aquí el
// set que usan los módulos. Acepta también alias estilo lucide que algunos manifests
// arrastran ('users', 'file-text'…). Fallback: cube-outline.
import {
  bagCheckOutline, bookmark, briefcase, calendarOutline, card, cartOutline,
  cashOutline, chatbubblesOutline, checkboxOutline, clipboardOutline, cube,
  cubeOutline, documentTextOutline, flameOutline, folderOutline, funnel,
  gridOutline, headsetOutline, layersOutline, mapOutline, peopleOutline,
  pricetag, pricetags, print, receiptOutline, send, settings, settingsOutline,
  shieldOutline, starOutline, statsChart, storefront, timeOutline, timerOutline, tv,
  warningOutline,
} from 'ionicons/icons';

const ICONS: Record<string, string> = {
  'bag-check-outline': bagCheckOutline,
  bookmark,
  briefcase,
  'calendar-outline': calendarOutline,
  card,
  'chatbubbles-outline': chatbubblesOutline,
  'checkbox-outline': checkboxOutline,
  'clipboard-outline': clipboardOutline,
  cube,
  'cube-outline': cubeOutline,
  'document-text-outline': documentTextOutline,
  'flame-outline': flameOutline,
  'folder-outline': folderOutline,
  funnel,
  'grid-outline': gridOutline,
  'headset-outline': headsetOutline,
  'layers-outline': layersOutline,
  'map-outline': mapOutline,
  'people-outline': peopleOutline,
  pricetag,
  pricetags,
  print,
  'receipt-outline': receiptOutline,
  send,
  settings,
  'settings-outline': settingsOutline,
  'shield-outline': shieldOutline,
  'star-outline': starOutline,
  'stats-chart': statsChart,
  storefront,
  'time-outline': timeOutline,
  'timer-outline': timerOutline,
  tv,
  'warning-outline': warningOutline,
  // Alias estilo lucide presentes en manifests antiguos.
  users: peopleOutline,
  'dollar-sign': cashOutline,
  'file-text': documentTextOutline,
  'shopping-cart': cartOutline,
};

/** SVG del icono declarado en el manifest, o cube-outline si no se conoce. */
export function manifestIcon(name?: string): string {
  return (name && ICONS[name]) || cubeOutline;
}
