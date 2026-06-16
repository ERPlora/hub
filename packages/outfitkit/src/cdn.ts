// Entry del bundle único de CDN (`@outfitkit/core/cdn` → dist/outfitkit.js). Importar este fichero
// auto-registra TODOS los componentes ok-*. Para una página de una vez (Django/landing/showcase)
// con un solo <script type="module">. `lit` external → en CDN sirve un import-map para "lit".

// Estado declarativo (registra <ok-store>; importa el singleton store al cargar)
import './components/ok-store/ok-store.js';
import './store/store.js';
// Compuesto / datos
import './components/ok-data-table/ok-data-table.js';
import './components/ok-mail/ok-mail.js';
// Componentes nuevos (huecos de Ionic)
import './components/ok-tree/ok-tree.js';
import './components/ok-inline-feedback/ok-inline-feedback.js';
import './components/ok-empty-state/ok-empty-state.js';
import './components/ok-kpi/ok-kpi.js';
import './components/ok-stat/ok-stat.js';
import './components/ok-stepper/ok-stepper.js';
import './components/ok-wizard/ok-wizard.js';
import './components/ok-widget-board/ok-widget-board.js';
import './components/ok-contact-form/ok-contact-form.js';
// Tier 1/2 (2ª oleada)
import './components/ok-calendar/ok-calendar.js';
import './components/ok-kanban/ok-kanban.js';
import './components/ok-app-launcher/ok-app-launcher.js';
import './components/ok-split-button/ok-split-button.js';
import './components/ok-combo/ok-combo.js';
import './components/ok-tag-input/ok-tag-input.js';
import './components/ok-rating/ok-rating.js';
import './components/ok-otp/ok-otp.js';
import './components/ok-pinpad/ok-pinpad.js';
import './components/ok-currency/ok-currency.js';
import './components/ok-phone/ok-phone.js';
import './components/ok-dropzone/ok-dropzone.js';
import './components/ok-sparkline/ok-sparkline.js';
import './components/ok-chat/ok-chat.js';
import './components/ok-scheduler/ok-scheduler.js';
import './components/ok-menubar/ok-menubar.js';
import './components/ok-carousel/ok-carousel.js';
import './components/ok-signature/ok-signature.js';
import './components/ok-qr/ok-qr.js';
import './components/ok-audio/ok-audio.js';
import './components/ok-video/ok-video.js';
import './components/ok-pdf/ok-pdf.js';
import './components/ok-receipt/ok-receipt.js';
import './components/ok-invoice/ok-invoice.js';
import './components/ok-timeline/ok-timeline.js';
import './components/ok-qty-stepper/ok-qty-stepper.js';
import './components/ok-command-palette/ok-command-palette.js';
import './components/ok-color-picker/ok-color-picker.js';
import './components/ok-avatar/ok-avatar.js';
import './components/ok-status-pill/ok-status-pill.js';
import './components/ok-drawer/ok-drawer.js';
import './components/ok-page-header/ok-page-header.js';
// Marketing 2026 (bento · cards · scroll-reveal · prueba social)
import './components/ok-bento/ok-bento.js';
import './components/ok-bento-item/ok-bento-item.js';
import './components/ok-reveal/ok-reveal.js';
import './components/ok-feature-card/ok-feature-card.js';
import './components/ok-pricing-card/ok-pricing-card.js';
import './components/ok-product-card/ok-product-card.js';
import './components/ok-logo-cloud/ok-logo-cloud.js';
import './components/ok-testimonial/ok-testimonial.js';
import './components/ok-cta-band/ok-cta-band.js';
import './components/ok-language-select/ok-language-select.js';
// Chrome web / marketing
import './components/ok-navbar/ok-navbar.js';
import './components/ok-footer/ok-footer.js';
import './components/ok-hero/ok-hero.js';
// ── ux-legacy port (Tier 1+2 huecos de Ionic) ─────────────────────────────────────────────────
import './components/ok-pagination/ok-pagination.js';
import './components/ok-skeleton/ok-skeleton.js';
import './components/ok-gauge/ok-gauge.js';
import './components/ok-chart/ok-chart.js';
import './components/ok-donut/ok-donut.js';
import './components/ok-heatmap/ok-heatmap.js';
import './components/ok-funnel/ok-funnel.js';
import './components/ok-bar-list/ok-bar-list.js';
import './components/ok-detail-list/ok-detail-list.js';
import './components/ok-icon-tile/ok-icon-tile.js';
import './components/ok-status-dot/ok-status-dot.js';
import './components/ok-kbd/ok-kbd.js';
import './components/ok-menu/ok-menu.js';
import './components/ok-hover-card/ok-hover-card.js';
import './components/ok-notification-center/ok-notification-center.js';
import './components/ok-coachmark/ok-coachmark.js';
import './components/ok-select-card/ok-select-card.js';
import './components/ok-error-page/ok-error-page.js';
import './components/ok-date-picker/ok-date-picker.js';
import './components/ok-time-picker/ok-time-picker.js';
import './components/ok-range-dual/ok-range-dual.js';
import './components/ok-file-item/ok-file-item.js';
import './components/ok-rich-text/ok-rich-text.js';
import './components/ok-code/ok-code.js';
import './components/ok-json-viewer/ok-json-viewer.js';
import './components/ok-diff/ok-diff.js';
import './components/ok-keyboard/ok-keyboard.js';
import './components/ok-calculator/ok-calculator.js';
import './components/ok-image/ok-image.js';
import './components/ok-gallery/ok-gallery.js';
import './components/ok-lightbox/ok-lightbox.js';
import './components/ok-cropper/ok-cropper.js';
import './components/ok-splitter/ok-splitter.js';
import './components/ok-loyalty-card/ok-loyalty-card.js';
import './components/ok-event-card/ok-event-card.js';
import './components/ok-avatar-group/ok-avatar-group.js';
import './components/ok-org-chart/ok-org-chart.js';
import './components/ok-file-manager/ok-file-manager.js';
