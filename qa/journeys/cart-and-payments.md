---
title: Llevar pedidos y pagos fuera del TPV
vertical: any
roles: responsable, administrador
---

Para qué: carritos que acaban en pedido, el cobro de esos pedidos y los pagos que el negocio registra, aprueba y completa.

## Punto de partida

- Un negocio con Carrito y pedidos y Pagos, y productos dados de alta.

## Recorrido

1. PAYMENT-F01 — el método de pago «Transferencia».
2. PAYMENT-F08 — el método, cambiado, desactivado y reactivado.
3. CART_CHECKOUT-F01 — un carrito para un cliente.
4. CART_CHECKOUT-F02 — dos productos al carrito, pedidos al asistente.
5. CART_CHECKOUT-F03 — una cantidad cambiada y una línea quitada.
6. CART_CHECKOUT-F12 — el carrito y sus líneas.
7. CART_CHECKOUT-F08 — el pedido, iniciado desde el carrito.
8. CART_CHECKOUT-F09 — el pedido, pagado.
9. CART_CHECKOUT-F11 — el pedido, completado.
10. CART_CHECKOUT-F10 — en otro pedido, el pago falla.
11. CART_CHECKOUT-F04 — otro carrito, vaciado.
12. CART_CHECKOUT-F05 — un carrito, abandonado.
13. CART_CHECKOUT-F07 — los carritos vencidos caducan.
14. CART_CHECKOUT-F06 — un carrito, borrado.
15. CART_CHECKOUT-F14 — un cliente pide borrar sus datos personales.
16. PAYMENT-F02 — un pago por transferencia.
17. PAYMENT-F03 — el pago, aprobado.
18. PAYMENT-F04 — enviado y después completado.
19. PAYMENT-F05 — otro pago, cancelado.
20. PAYMENT-F06 — los pagos, buscados y revisados.
