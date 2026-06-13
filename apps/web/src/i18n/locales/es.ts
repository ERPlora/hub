// Textos del shell (chrome) en español. Solo cubre la navegación, la topbar y el footer del
// sidebar — NO los textos de cada vista (eso se irá migrando por pantalla). Mantener plano y
// agrupado por zona para que sea fácil de extender.
export default {
  nav: {
    general: 'General',
    account: 'Cuenta',
    modules: 'Módulos',
    home: 'Inicio',
    employees: 'Empleados',
    billing: 'Facturación',
    marketplace: 'Marketplace',
    system: 'Sistema',
    settings: 'Ajustes',
  },
  topbar: {
    back: 'Atrás',
    apps: 'Aplicaciones',
    appsEmpty: 'No tienes módulos instalados. Abre la tienda para añadir.',
    assistant: 'Asistente',
    notifications: 'Notificaciones',
    toggleTheme: 'Cambiar tema',
    profile: 'Perfil',
    menu: 'Abrir menú',
    collapseMenu: 'Colapsar menú',
    expandMenu: 'Expandir menú',
  },
  sidebar: {
    profile: 'Perfil',
    installApp: 'Instalar app',
    reportProblem: 'Reportar un problema',
    signOut: 'Cerrar sesión',
  },
  assistant: {
    title: 'Asistente',
    empty: 'Pregúntame por tus ventas, tu inventario o cualquier cosa de tu negocio.',
    placeholder: 'Escribe un mensaje…',
    send: 'Enviar',
    stop: 'Detener',
    close: 'Cerrar',
    noReply: '(sin respuesta)',
    error: 'No se pudo contactar con el asistente.',
  },
  bugReport: {
    title: 'Reportar un problema',
    description: 'Cuéntanos qué ha pasado',
    placeholder: 'Describe el problema con el mayor detalle posible…',
    submit: 'Enviar',
    cancel: 'Cancelar',
    sent: 'Gracias, hemos recibido tu reporte.',
    failed: 'No se pudo enviar el reporte. Inténtalo de nuevo.',
  },
} as const;
