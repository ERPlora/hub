// Sesión de inspección manual: abre Chromium visible contra la app del Hub y lo DEJA ABIERTO
// hasta que el usuario cierre la ventana o cancele el proceso. No automatiza nada: solo abre
// el navegador en la página de login para que el humano revise a mano.
import { chromium } from 'playwright';

const URL = process.env.ERPLORA_URL || 'http://localhost:5173/';

const browser = await chromium.launch({ headless: false });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
await page.goto(URL, { waitUntil: 'domcontentloaded' });

console.log(`\n✓ Navegador abierto en ${URL}`);
console.log('Login: usuario "Demo" · PIN "0000"');
console.log('El navegador se mantendrá abierto. Cierra la ventana o detén el proceso cuando termines.\n');

// Mantén el proceso vivo hasta que el usuario cierre la ventana manualmente.
await new Promise((resolve) => {
  context.on('close', resolve);
  browser.on('disconnected', resolve);
});

console.log('Navegador cerrado. Saliendo.');
await browser.close();
