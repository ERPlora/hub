// @outfitkit/core — barrel. Importar este módulo registra TODOS los componentes ok-* y re-exporta
// sus clases y tipos. Para tree-shake real, importa el componente concreto:
//   import '@outfitkit/core/ok-tree';

// ── Estado (store reactivo + IndexedDB) ───────────────────────────────────────────────────
export { createStore, store } from './store/store.js';
export type { Store, StoreOptions, StoreSubscriber } from './store/store.js';
export { StoreController } from './store/controller.js';
export { OkStore } from './components/ok-store/ok-store.js';

// ── Compuesto / datos ─────────────────────────────────────────────────────────────────────
export { OkDataTable } from './components/ok-data-table/ok-data-table.js';
export type {
  DataTableColumn,
  DataTableAction,
  DataTableView,
  DataTablePrimaryAction,
  DataTableRowKey,
} from './components/ok-data-table/ok-data-table.js';
export { OkMail } from './components/ok-mail/ok-mail.js';
export type { OkMailFolder, OkMailMessage } from './components/ok-mail/ok-mail.js';

// ── Componentes nuevos (huecos de Ionic) ────────────────────────────────────────────────────
export { OkTree } from './components/ok-tree/ok-tree.js';
export type { OkTreeNode } from './components/ok-tree/ok-tree.js';
export { OkInlineFeedback } from './components/ok-inline-feedback/ok-inline-feedback.js';
export type { OkInlineFeedbackTone } from './components/ok-inline-feedback/ok-inline-feedback.js';
export { OkEmptyState } from './components/ok-empty-state/ok-empty-state.js';
export { OkKpi } from './components/ok-kpi/ok-kpi.js';
export { OkStat } from './components/ok-stat/ok-stat.js';
export { OkStepper } from './components/ok-stepper/ok-stepper.js';
export type { OkStep } from './components/ok-stepper/ok-stepper.js';
export { OkWizard } from './components/ok-wizard/ok-wizard.js';
export { OkWidgetBoard } from './components/ok-widget-board/ok-widget-board.js';
export type { WidgetDef, WidgetPreset, WidgetSize, OkWidgetBoardLabels } from './components/ok-widget-board/ok-widget-board.js';
export { OkContactForm } from './components/ok-contact-form/ok-contact-form.js';
export { OkCalendar } from './components/ok-calendar/ok-calendar.js';
export type { OkCalendarEvent, OkCalendarView } from './components/ok-calendar/ok-calendar.js';
export { OkKanban } from './components/ok-kanban/ok-kanban.js';
export type { OkKanbanColumn, OkKanbanCard } from './components/ok-kanban/ok-kanban.js';
export { OkAppLauncher } from './components/ok-app-launcher/ok-app-launcher.js';
export type { OkLauncherApp } from './components/ok-app-launcher/ok-app-launcher.js';
export { OkSplitButton } from './components/ok-split-button/ok-split-button.js';
export type { OkSplitButtonItem } from './components/ok-split-button/ok-split-button.js';
export { OkCombo } from './components/ok-combo/ok-combo.js';
export type { OkComboOption } from './components/ok-combo/ok-combo.js';
export { OkTagInput } from './components/ok-tag-input/ok-tag-input.js';
export { OkRating } from './components/ok-rating/ok-rating.js';
export { OkOtp } from './components/ok-otp/ok-otp.js';
export { OkPinpad } from './components/ok-pinpad/ok-pinpad.js';
export { OkCurrency } from './components/ok-currency/ok-currency.js';
export { OkPhone } from './components/ok-phone/ok-phone.js';
export type { OkPhoneCountry } from './components/ok-phone/ok-phone.js';
export { OkDropzone } from './components/ok-dropzone/ok-dropzone.js';
export { OkSparkline } from './components/ok-sparkline/ok-sparkline.js';
export { OkChat } from './components/ok-chat/ok-chat.js';
export type { OkChatMessage } from './components/ok-chat/ok-chat.js';
export { OkScheduler } from './components/ok-scheduler/ok-scheduler.js';
export type { OkSchedulerResource, OkSchedulerEvent } from './components/ok-scheduler/ok-scheduler.js';
export { OkMenubar } from './components/ok-menubar/ok-menubar.js';
// `OkMenu`/`OkMenuItem` del menubar se re-exportan con alias para no chocar con la clase
// `OkMenu` del nuevo componente ok-menu (dropdown). El menubar en sí no cambia.
export type { OkMenu as OkMenubarMenu, OkMenuItem as OkMenubarMenuItem } from './components/ok-menubar/ok-menubar.js';
export { OkCarousel } from './components/ok-carousel/ok-carousel.js';
export { OkSignature } from './components/ok-signature/ok-signature.js';
export { OkQr } from './components/ok-qr/ok-qr.js';
export { OkAudio } from './components/ok-audio/ok-audio.js';
export { OkVideo } from './components/ok-video/ok-video.js';
export { OkPdf } from './components/ok-pdf/ok-pdf.js';
export { OkReceipt } from './components/ok-receipt/ok-receipt.js';
export type {
  ReceiptData,
  ReceiptLine,
  ReceiptTax,
  ReceiptPayment,
  ReceiptBusiness,
} from './components/ok-receipt/ok-receipt.js';
export { OkInvoice } from './components/ok-invoice/ok-invoice.js';
export type {
  InvoiceData,
  InvoiceParty,
  InvoiceLine,
  InvoiceTaxLine,
} from './components/ok-invoice/ok-invoice.js';
export { OkTimeline } from './components/ok-timeline/ok-timeline.js';
export type { OkTimelineItem } from './components/ok-timeline/ok-timeline.js';
export { OkQtyStepper } from './components/ok-qty-stepper/ok-qty-stepper.js';
export { OkCommandPalette } from './components/ok-command-palette/ok-command-palette.js';
export type { OkCommand } from './components/ok-command-palette/ok-command-palette.js';
export { OkColorPicker } from './components/ok-color-picker/ok-color-picker.js';
export type { OkRgb } from './components/ok-color-picker/ok-color-picker.js';
export { OkAvatar } from './components/ok-avatar/ok-avatar.js';
export type { OkAvatarSize, OkAvatarShape, OkAvatarTone, OkAvatarStatus } from './components/ok-avatar/ok-avatar.js';
export { OkStatusPill } from './components/ok-status-pill/ok-status-pill.js';
export type { OkStatusPillTone, OkStatusPillSize } from './components/ok-status-pill/ok-status-pill.js';
export { OkDrawer } from './components/ok-drawer/ok-drawer.js';
export type { OkDrawerSide, OkDrawerLabels } from './components/ok-drawer/ok-drawer.js';
export { OkPageHeader } from './components/ok-page-header/ok-page-header.js';

// ── Marketing 2026 (bento · cards · scroll-reveal · prueba social) ───────────────────────────
export { OkBento } from './components/ok-bento/ok-bento.js';
export { OkBentoItem } from './components/ok-bento-item/ok-bento-item.js';
export { OkReveal } from './components/ok-reveal/ok-reveal.js';
export { OkFeatureCard } from './components/ok-feature-card/ok-feature-card.js';
export { OkPricingCard } from './components/ok-pricing-card/ok-pricing-card.js';
export { OkProductCard } from './components/ok-product-card/ok-product-card.js';
export { OkLogoCloud } from './components/ok-logo-cloud/ok-logo-cloud.js';
export { OkTestimonial } from './components/ok-testimonial/ok-testimonial.js';
export { OkCtaBand } from './components/ok-cta-band/ok-cta-band.js';
export { OkLanguageSelect } from './components/ok-language-select/ok-language-select.js';

// ── Chrome web / marketing ──────────────────────────────────────────────────────────────────
export { OkNavbar } from './components/ok-navbar/ok-navbar.js';
export { OkFooter } from './components/ok-footer/ok-footer.js';
export { OkHero } from './components/ok-hero/ok-hero.js';

// ── ux-legacy port (Tier 1+2 huecos de Ionic) ─────────────────────────────────────────────────
export { OkPagination } from './components/ok-pagination/ok-pagination.js';
export type { PaginationVariant } from './components/ok-pagination/ok-pagination.js';
export { OkSkeleton } from './components/ok-skeleton/ok-skeleton.js';
export type { OkSkeletonVariant, OkSkeletonPreset } from './components/ok-skeleton/ok-skeleton.js';
export { OkGauge } from './components/ok-gauge/ok-gauge.js';
export type { OkGaugeThreshold, OkGaugeType } from './components/ok-gauge/ok-gauge.js';
export { OkChart } from './components/ok-chart/ok-chart.js';
export type { OkChartSeries, OkChartType } from './components/ok-chart/ok-chart.js';
export { OkDonut } from './components/ok-donut/ok-donut.js';
export type { OkDonutSlice } from './components/ok-donut/ok-donut.js';
export { OkHeatmap } from './components/ok-heatmap/ok-heatmap.js';
export type { OkHeatmapCell, OkHeatmapLayout } from './components/ok-heatmap/ok-heatmap.js';
export { OkFunnel } from './components/ok-funnel/ok-funnel.js';
export type { OkFunnelColor, OkFunnelStep } from './components/ok-funnel/ok-funnel.js';
export { OkBarList } from './components/ok-bar-list/ok-bar-list.js';
export type { BarListColor, BarListValueFormat, BarListItem } from './components/ok-bar-list/ok-bar-list.js';
export { OkDetailList } from './components/ok-detail-list/ok-detail-list.js';
export type { OkDetailItem } from './components/ok-detail-list/ok-detail-list.js';
export { OkIconTile } from './components/ok-icon-tile/ok-icon-tile.js';
export type { OkIconTileColor, OkIconTileSize, OkIconTileShape } from './components/ok-icon-tile/ok-icon-tile.js';
export { OkStatusDot } from './components/ok-status-dot/ok-status-dot.js';
export type { OkStatusDotTone, OkStatusDotSize } from './components/ok-status-dot/ok-status-dot.js';
export { OkKbd } from './components/ok-kbd/ok-kbd.js';
export type { OkKbdSize } from './components/ok-kbd/ok-kbd.js';
export { OkMenu } from './components/ok-menu/ok-menu.js';
export type { OkMenuEntry, OkMenuAnchor, OkMenuWidth, OkMenuTrigger } from './components/ok-menu/ok-menu.js';
export { OkHoverCard } from './components/ok-hover-card/ok-hover-card.js';
export type { OkHoverCardStat, OkHoverCardAction, OkHoverCardPlacement, OkHoverCardLabels } from './components/ok-hover-card/ok-hover-card.js';
export { OkNotificationCenter } from './components/ok-notification-center/ok-notification-center.js';
export type { OkNotifVariant, OkNotification, OkNotifFilter, OkNotifLabels } from './components/ok-notification-center/ok-notification-center.js';
export { OkCoachmark } from './components/ok-coachmark/ok-coachmark.js';
export type { OkCoachStep, OkCoachPlacement, OkCoachmarkLabels } from './components/ok-coachmark/ok-coachmark.js';
export { OkSelectCard } from './components/ok-select-card/ok-select-card.js';
export type { OkSelectCardChangeDetail } from './components/ok-select-card/ok-select-card.js';
export { OkErrorPage } from './components/ok-error-page/ok-error-page.js';
export type { OkErrorPageVariant, OkErrorPageMode, OkErrorCheckStatus, OkErrorShortcut, OkErrorCheck } from './components/ok-error-page/ok-error-page.js';
export { OkDatePicker } from './components/ok-date-picker/ok-date-picker.js';
export type { OkDatePickerMode, OkDateRange, OkDatePickerValue, OkDatePreset, OkDatePickerLabels } from './components/ok-date-picker/ok-date-picker.js';
export { OkTimePicker } from './components/ok-time-picker/ok-time-picker.js';
export { OkRangeDual } from './components/ok-range-dual/ok-range-dual.js';
export type { OkRangeDualChangeDetail } from './components/ok-range-dual/ok-range-dual.js';
export { OkFileItem } from './components/ok-file-item/ok-file-item.js';
export type { OkFileItemState } from './components/ok-file-item/ok-file-item.js';
export { OkRichText } from './components/ok-rich-text/ok-rich-text.js';
export type { OkRichTextSize } from './components/ok-rich-text/ok-rich-text.js';
export { OkCode } from './components/ok-code/ok-code.js';
export type { OkCodeCopyDetail } from './components/ok-code/ok-code.js';
export { OkJsonViewer } from './components/ok-json-viewer/ok-json-viewer.js';
export type { OkJsonViewerSize, OkJsonValue } from './components/ok-json-viewer/ok-json-viewer.js';
export { OkDiff } from './components/ok-diff/ok-diff.js';
export type { OkDiffLineType, OkDiffLine } from './components/ok-diff/ok-diff.js';
export { OkKeyboard } from './components/ok-keyboard/ok-keyboard.js';
export type { OkKeyboardLayout, OkKeyboardDensity } from './components/ok-keyboard/ok-keyboard.js';
export { OkCalculator } from './components/ok-calculator/ok-calculator.js';
export type { OkCalculatorOp, OkCalculatorInputDetail, OkCalculatorChangeDetail } from './components/ok-calculator/ok-calculator.js';
export { OkImage } from './components/ok-image/ok-image.js';
export type { OkImageRatio, OkImageRadius, OkImageZoom } from './components/ok-image/ok-image.js';
export { OkGallery } from './components/ok-gallery/ok-gallery.js';
export type { OkGalleryImage } from './components/ok-gallery/ok-gallery.js';
export { OkLightbox } from './components/ok-lightbox/ok-lightbox.js';
export type { OkLightboxItemType, OkLightboxItem, OkLightboxLabels } from './components/ok-lightbox/ok-lightbox.js';
export { OkCropper } from './components/ok-cropper/ok-cropper.js';
export type { OkCropperAspect, OkCropRect, OkCropDetail } from './components/ok-cropper/ok-cropper.js';
export { OkSplitter } from './components/ok-splitter/ok-splitter.js';
export type { OkSplitterOrientation, OkSplitterCollapsed } from './components/ok-splitter/ok-splitter.js';
export { OkLoyaltyCard } from './components/ok-loyalty-card/ok-loyalty-card.js';
export type { OkLoyaltyTier, OkLoyaltySize } from './components/ok-loyalty-card/ok-loyalty-card.js';
export { OkEventCard } from './components/ok-event-card/ok-event-card.js';
export type { OkEventCardColor, OkEventCardSize, OkEventAttendee } from './components/ok-event-card/ok-event-card.js';
export { OkAvatarGroup } from './components/ok-avatar-group/ok-avatar-group.js';
export type { OkAvatarGroupSize, OkAvatarItem } from './components/ok-avatar-group/ok-avatar-group.js';
export { OkOrgChart } from './components/ok-org-chart/ok-org-chart.js';
export type { OrgNode } from './components/ok-org-chart/ok-org-chart.js';
export { OkFileManager } from './components/ok-file-manager/ok-file-manager.js';
export type { OkFmFolder, OkFmFile, OkFmCrumb, OkFmQuota, OkFmView, OkFmLabels } from './components/ok-file-manager/ok-file-manager.js';
