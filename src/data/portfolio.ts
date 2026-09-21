export type Locale = "es" | "en";

export type LabStatus = "active";

interface LabBase {
  id: string;
  title: string;
  summary: string;
  status: LabStatus;
  statusLabel: string;
  technologies: string[];
}

export interface RelayLab extends LabBase {
  kind: "relay";
  addressLabel: string;
  addressPending: string;
  copyLabel: string;
  copiedLabel: string;
  checkingLabel: string;
  onlineLabel: string;
  offlineLabel: string;
  inboxLabel: string;
  inboxEmpty: string;
  inboxNote: string;
  officialLinkLabel: string;
  wizard: {
    title: string;
    copy: string;
    steps: [string, string, string, string];
    openLabel: string;
    closeLabel: string;
    sourcePending: string;
    sourceLabel: string;
    destinationLabel: string;
    messageLabel: string;
    messagePlaceholder: string;
    sendLabel: string;
    preparingLabel: string;
    unavailableLabel: string;
    queuedLabel: string;
    deliveredLabel: string;
    failedLabel: string;
    routeWaitingLabel: string;
    routeSourceReadyLabel: string;
    routeEncryptedLabel: string;
    routeRoutingLabel: string;
    routeReceivedLabel: string;
    routeConfirmedLabel: string;
    routeDeliveryFailedLabel: string;
    routeOutboundFailedLabel: string;
    routeUnknownFailedLabel: string;
    telegramLabel: string;
    telegramConfiguredLabel: string;
    telegramUnavailableLabel: string;
    telegramCopy: string;
  };
}

export const relayNodeCopy = {
  es: {
    label: "Conexiones TCP Reticulum",
    unavailable: "El estado de los nodos no está disponible.",
    up: "Online",
    down: "Offline",
    note: "Los nombres identifican conexiones TCP configuradas. La dirección LXMF no pertenece a un nodo concreto: cualquier cliente con conectividad Reticulum puede descubrirla. El estado no garantiza una ruta ni una entrega.",
    sessionLabel: "Nodo seleccionado para esta prueba",
    sessionPending: "Pendiente de selección de ruta",
  },
  en: {
    label: "Reticulum TCP connections",
    unavailable: "Node status is unavailable.",
    up: "Online",
    down: "Offline",
    note: "Names identify configured TCP connections. The LXMF address does not belong to one specific node: any client with Reticulum connectivity can discover it. This state does not guarantee a route or delivery.",
    sessionLabel: "Node selected for this test",
    sessionPending: "Waiting for route selection",
  },
} as const;

export interface MetricsLab extends LabBase {
  kind: "metrics";
  titleLabel: string;
  cpuLabel: string;
  memoryLabel: string;
  servicesLabel: string;
  startLabel: string;
  endLabel: string;
  applyLabel: string;
  previousLabel: string;
  nextLabel: string;
  nowLabel: string;
  loadingLabel: string;
  unavailableLabel: string;
  noDataLabel: string;
}

export interface HomeStatusLab extends LabBase {
  kind: "home-status";
  loadingLabel: string;
  unavailableLabel: string;
  availableLabel: string;
  temperatureLabel: string;
  humidityLabel: string;
  airQualityLabel: string;
  goodLabel: string;
  regularLabel: string;
  badLabel: string;
  privacyTitle: string;
  privacyCopy: string;
}

export const profile = {
  name: "David Estaben",
  email: "estaben.sti@gmail.com",
  socialLinks: [
    { label: "GitHub", url: "https://github.com/destaben" },
    { label: "LinkedIn", url: "https://www.linkedin.com/in/david-estab%C3%A9n-8067b843/" },
  ],
};

export const labSummaries: Record<Locale, Record<string, string>> = {
  es: {
    "signal-relay": "Un punto de contacto Reticulum autohospedado para recibir mensajes desde clientes compatibles. El recorrido guiado permite entender cómo se prepara, cifra y confirma una prueba antes de enviarla.",
    "container-metrics": "Uso de CPU y memoria agregado de los servicios de mi servidor personal, consultado a través de Prometheus. Puedes comparar ambos recursos, seleccionar servicios y revisar un intervalo concreto.",
    "home-status": "Temperatura, humedad y calidad del aire interior como una lectura agregada del hogar. Sirve para consultar el estado actual de mi hogar manteniendo la privacidad.",
  },
  en: {
    "signal-relay": "A self-hosted Reticulum contact point for receiving messages from compatible clients. The guided journey shows how a test is prepared, encrypted, and confirmed before it is sent.",
    "container-metrics": "Aggregated CPU and memory use from my personal server services, queried through Prometheus. Compare both resources, select services, and inspect a specific time range.",
    "home-status": "Indoor temperature, humidity, and air quality as an aggregate home reading. Check the current state of my home while preserving privacy.",
  },
};

export const portfolio = {
  es: {
    language: "ES", switchLanguage: "English", switchHref: "/en/",
    description: "David Estaben, ingeniero de fiabilidad y software especializado en plataformas, observabilidad y automatización.",
    navigation: [{ label: "Trabajo", href: "#trabajo" }, { label: "Laboratorio", href: "#laboratorio" }, { label: "Proyectos", href: "#proyectos" }, { label: "Bitácora", href: "#bitacora" }, { label: "Trayectoria", href: "#trayectoria" }, { label: "Contacto", href: "#contacto" }],
    hero: { eyebrow: "Ingeniería de fiabilidad y plataformas", title: "Sistemas claros. Equipos seguros.", copy: "Soy Site Reliability Engineer y desarrollador de software. Diseño automatización, observabilidad y plataformas cloud con una idea sencilla: reducir incertidumbre para que los equipos puedan centrarse en entregar valor.", primary: "Ver experiencia", secondary: "Contacto Reticulum" },
    proof: ["SRE y desarrollo de software", "Zaragoza · remoto", "Abierto a oportunidades y colaboración"],
    work: { label: "Áreas de trabajo", title: "Fiabilidad construida desde la práctica.", copy: "Mi trabajo combina visión de producto, criterio operativo y atención al detalle: entender el contexto, eliminar fricción y dejar una base más mantenible.", cases: [
      { number: "01", title: "Sistemas observables", context: "Instrumentación y señales útiles para que los equipos puedan detectar, entender y priorizar problemas con rapidez.", decision: "Convertir datos técnicos en contexto accionable para operación y desarrollo.", tags: ["Observabilidad", "SRE", "Python"] },
      { number: "02", title: "Plataformas que escalan", context: "Entornos de entrega y ejecución que evolucionan sin depender de pasos manuales ni conocimiento aislado.", decision: "Aplicar infraestructura como código, estándares de entrega y automatización que simplifican el cambio.", tags: ["Kubernetes", "Terraform", "CI/CD"] },
      { number: "03", title: "Cloud con criterio", context: "Experiencia en infraestructura, integración y optimización de costes en distintos entornos cloud.", decision: "Equilibrar disponibilidad, seguridad, coste y mantenibilidad en cada decisión técnica.", tags: ["Cloud", "FinOps", "Integración"] },
    ] },
    lab: { label: "Laboratorio", title: "Sistemas reales, explicados desde su uso.", copy: "Cada laboratorio muestra una parte acotada de un sistema que uso: comunicación resiliente, observabilidad y domótica. Explica qué información se expone, qué puedes explorar y qué queda deliberadamente protegido." },
    labs: [
      { id: "signal-relay", kind: "relay", title: "Reticulum", summary: "Un punto de contacto Reticulum autohospedado para recibir mensajes desde clientes compatibles.", status: "active", statusLabel: "Activo", technologies: ["Reticulum", "FastAPI"], addressLabel: "Dirección Reticulum", addressPending: "Dirección disponible al publicar el nodo", copyLabel: "Copiar", copiedLabel: "Copiada", checkingLabel: "Comprobando Reticulum", onlineLabel: "Reticulum online", offlineLabel: "Reticulum offline", inboxLabel: "Mensajes recibidos", inboxEmpty: "Todavía no hay mensajes registrados.", inboxNote: "Los mensajes se muestran como texto plano y se conservan de forma limitada.", officialLinkLabel: "Web oficial de Reticulum", wizard: { title: "Recorrido Reticulum", copy: "La identidad temporal se crea sólo al enviar esta prueba. El navegador no recibe claves privadas ni se conecta directamente a Reticulum.", steps: ["Origen temporal", "Destino Reticulum", "Cifrado", "Confirmación"], openLabel: "Explorar recorrido Reticulum", closeLabel: "Cerrar recorrido", sourcePending: "Se crea al enviar la prueba", sourceLabel: "Origen temporal", destinationLabel: "Destino de David", messageLabel: "Nota para esta prueba", messagePlaceholder: "Escribe un mensaje breve", sendLabel: "Enviar prueba", preparingLabel: "Preparando sesión segura", unavailableLabel: "El envío educativo no está habilitado en este nodo.", queuedLabel: "Mensaje en cola", deliveredLabel: "Entrega confirmada", failedLabel: "No se pudo entregar", routeWaitingLabel: "Pendiente", routeSourceReadyLabel: "Identidad temporal preparada", routeEncryptedLabel: "Mensaje cifrado por Reticulum", routeRoutingLabel: "Esperando acuse de la ruta", routeReceivedLabel: "Recibido por Reticulum", routeConfirmedLabel: "Acuse de Reticulum confirmado", routeDeliveryFailedLabel: "El destino no confirmó la entrega", routeOutboundFailedLabel: "El nodo no pudo emitir el mensaje", routeUnknownFailedLabel: "La entrega terminó con un error", telegramLabel: "Aviso Telegram", telegramConfiguredLabel: "Telegram configurado", telegramUnavailableLabel: "Telegram no configurado", telegramCopy: "Cuando Reticulum recibe el mensaje, puede enviar un aviso privado por Telegram." } },
      { id: "container-metrics", kind: "metrics", title: "Observabilidad de servicios", summary: "Uso de CPU y memoria de los servicios de mi servidor personal, consultado a través de Prometheus.", status: "active", statusLabel: "En directo", technologies: ["Prometheus", "Contenedores"], titleLabel: "Métricas de servicios", cpuLabel: "CPU", memoryLabel: "Memoria", servicesLabel: "Servicios", startLabel: "Inicio", endLabel: "Fin", applyLabel: "Aplicar", previousLabel: "Intervalo anterior", nextLabel: "Intervalo siguiente", nowLabel: "Volver a ahora", loadingLabel: "Cargando métricas", unavailableLabel: "Las métricas no están disponibles ahora.", noDataLabel: "No hay muestras en este intervalo." },
      { id: "home-status", kind: "home-status", title: "Monitorización y automatización del hogar", summary: "Temperatura, humedad y calidad del aire interior.", status: "active", statusLabel: "Activo", technologies: ["Home Assistant", "Privacidad"], loadingLabel: "Consultando estado", unavailableLabel: "El estado no está disponible ahora.", availableLabel: "Actualizado", temperatureLabel: "Temperatura", humidityLabel: "Humedad", airQualityLabel: "Calidad ambiental", goodLabel: "Buena", regularLabel: "Regular", badLabel: "Mala", privacyTitle: "Datos protegidos", privacyCopy: "No se publica presencia, cámaras, cerraduras, dispositivos ni habitaciones." },
    ] satisfies (RelayLab | MetricsLab | HomeStatusLab)[],
    experience: { label: "Trayectoria", title: "Experiencia en software, cloud y operaciones.", items: [
      { period: "abr 2021 - hoy", role: "Site Reliability Engineer", company: "adidas", focus: "Fiabilidad de servicios, automatización y orquestación." },
      { period: "may 2020 - abr 2021", role: "Cloud Engineer", company: "NTT", focus: "Infraestructura cloud, optimización de costes e integración." },
      { period: "ene 2019 - abr 2020", role: "Senior DevOps Engineer", company: "dareCode", focus: "Automatización, contenedores y plataformas de entrega." },
      { period: "abr 2018 - ene 2019", role: "Desarrollador", company: "NSC Network Solutions Control", focus: "Desarrollo web, administración de Docker y mantenimiento de sistemas." },
      { period: "jul 2017 - feb 2018", role: "Integrador de sistemas", company: "Orbe", focus: "Integración de seguridad, redes, telefonía y sistemas Linux y Windows." },
      { period: "mar 2012 - jun 2017", role: "Proyectista", company: "A&T Ingeniería", focus: "Proyectos de telecomunicaciones, sistemas, desarrollo e integración KNX." },
    ] },
    contact: { label: "Contacto", title: "Una buena conversación puede empezar por un problema difícil.", copy: "Estoy interesado en puestos de SRE, ingeniería de plataformas y software donde la fiabilidad sea una responsabilidad compartida. También agradezco conversaciones sobre observabilidad, infraestructura como código y sistemas distribuidos.", emailLabel: "Correo", networkLabel: "Red profesional", response: "Suelo responder personalmente. Para una primera toma de contacto, basta con contexto sobre el reto y el equipo.", action: "Escribir a David" },
    footer: "Ingeniería de sistemas con criterio operativo.",
  },
  en: {
    language: "EN", switchLanguage: "Español", switchHref: "/es/",
    description: "David Estaben is a reliability and software engineer focused on platforms, observability, and automation.",
    navigation: [{ label: "Work", href: "#work" }, { label: "Lab", href: "#lab" }, { label: "Projects", href: "#projects" }, { label: "Notes", href: "#notes" }, { label: "Experience", href: "#experience" }, { label: "Contact", href: "#contact" }],
    hero: { eyebrow: "Reliability and platform engineering", title: "Clear systems. Confident teams.", copy: "I am a Site Reliability Engineer and software developer. I build automation, observability, and cloud platforms around one simple idea: reduce uncertainty so teams can focus on delivering value.", primary: "Explore my work", secondary: "Reticulum contact" },
    proof: ["SRE and software engineering", "Zaragoza · remote", "Open to roles and collaboration"],
    work: { label: "Areas of work", title: "Reliability grounded in practice.", copy: "My work brings together product awareness, operational judgement, and care for detail: understand the context, remove friction, and leave a more maintainable foundation.", cases: [
      { number: "01", title: "Observable systems", context: "Instrumentation and useful signals that help teams detect, understand, and prioritise issues quickly.", decision: "Turn technical data into actionable context for operations and development.", tags: ["Observability", "SRE", "Python"] },
      { number: "02", title: "Platforms that scale", context: "Delivery and runtime environments that can evolve without manual steps or isolated knowledge.", decision: "Apply infrastructure as code, delivery standards, and automation that make change easier.", tags: ["Kubernetes", "Terraform", "CI/CD"] },
      { number: "03", title: "Cloud with judgement", context: "Experience across infrastructure, integration, and cost optimisation in varied cloud environments.", decision: "Balance availability, security, cost, and maintainability in every technical decision.", tags: ["Cloud", "FinOps", "Integration"] },
    ] },
    lab: { label: "Lab", title: "Systems explained through use.", copy: "Each lab shows a bounded part of a system I use: resilient communication, observability, and home automation. It explains what information is exposed, what you can explore, and what is deliberately protected." },
    labs: [
      { id: "signal-relay", kind: "relay", title: "Reticulum", summary: "A self-hosted Reticulum contact point for receiving messages from compatible clients.", status: "active", statusLabel: "Active", technologies: ["Reticulum", "FastAPI"], addressLabel: "Reticulum address", addressPending: "Address available once the node is published", copyLabel: "Copy", copiedLabel: "Copied", checkingLabel: "Checking Reticulum", onlineLabel: "Reticulum online", offlineLabel: "Reticulum offline", inboxLabel: "Received messages", inboxEmpty: "No messages have been recorded yet.", inboxNote: "Messages are shown as plain text and retained for a limited time.", officialLinkLabel: "Reticulum official website", wizard: { title: "Reticulum journey", copy: "The temporary identity is created only when this test is sent. The browser never receives private keys or connects directly to Reticulum.", steps: ["Temporary source", "Reticulum destination", "Encryption", "Confirmation"], openLabel: "Explore the Reticulum journey", closeLabel: "Close journey", sourcePending: "Created when the test is sent", sourceLabel: "Temporary source", destinationLabel: "David's destination", messageLabel: "Note for this test", messagePlaceholder: "Write a short message", sendLabel: "Send test", preparingLabel: "Preparing secure session", unavailableLabel: "Educational sending is not enabled on this node.", queuedLabel: "Message queued", deliveredLabel: "Delivery confirmed", failedLabel: "Delivery failed", routeWaitingLabel: "Waiting", routeSourceReadyLabel: "Temporary identity prepared", routeEncryptedLabel: "Message encrypted by Reticulum", routeRoutingLabel: "Waiting for route acknowledgement", routeReceivedLabel: "Received by Reticulum", routeConfirmedLabel: "Reticulum acknowledgement confirmed", routeDeliveryFailedLabel: "The destination did not confirm delivery", routeOutboundFailedLabel: "The node could not emit the message", routeUnknownFailedLabel: "Delivery ended with an error", telegramLabel: "Telegram notice", telegramConfiguredLabel: "Telegram configured", telegramUnavailableLabel: "Telegram not configured", telegramCopy: "When Reticulum receives the message, it can send a private Telegram notification." } },
      { id: "container-metrics", kind: "metrics", title: "Service observability", summary: "CPU and memory use from my personal server services, queried through Prometheus.", status: "active", statusLabel: "Live", technologies: ["Prometheus", "Containers"], titleLabel: "Service metrics", cpuLabel: "CPU", memoryLabel: "Memory", servicesLabel: "Services", startLabel: "Start", endLabel: "End", applyLabel: "Apply", previousLabel: "Previous interval", nextLabel: "Next interval", nowLabel: "Back to now", loadingLabel: "Loading metrics", unavailableLabel: "Metrics are unavailable right now.", noDataLabel: "There are no samples in this interval." },
      { id: "home-status", kind: "home-status", title: "Home monitoring and automation", summary: "Indoor temperature, humidity, and air quality.", status: "active", statusLabel: "Active", technologies: ["Home Assistant", "Privacy"], loadingLabel: "Checking status", unavailableLabel: "Home status is unavailable right now.", availableLabel: "Updated", temperatureLabel: "Temperature", humidityLabel: "Humidity", airQualityLabel: "Air quality", goodLabel: "Good", regularLabel: "Regular", badLabel: "Bad", privacyTitle: "Protected data", privacyCopy: "Presence, cameras, locks, devices, and rooms are not published." },
    ] satisfies (RelayLab | MetricsLab | HomeStatusLab)[],
    experience: { label: "Experience", title: "Experience across software, cloud, and operations.", items: [
      { period: "Apr 2021 - present", role: "Site Reliability Engineer", company: "adidas", focus: "Service reliability, automation, and orchestration." },
      { period: "May 2020 - Apr 2021", role: "Cloud Engineer", company: "NTT", focus: "Cloud infrastructure, cost optimisation, and integration." },
      { period: "Jan 2019 - Apr 2020", role: "Senior DevOps Engineer", company: "dareCode", focus: "Automation, containers, and delivery platforms." },
      { period: "Apr 2018 - Jan 2019", role: "Software Developer", company: "NSC Network Solutions Control", focus: "Web development, Docker administration, and systems maintenance." },
      { period: "Jul 2017 - Feb 2018", role: "Systems Integrator", company: "Orbe", focus: "Security, network, telephony, and Linux and Windows systems integration." },
      { period: "Mar 2012 - Jun 2017", role: "Project Designer", company: "A&T Ingeniería", focus: "Telecommunications, systems, software development, and KNX integration projects." },
    ] },
    contact: { label: "Contact", title: "A good conversation can start with a difficult problem.", copy: "I am interested in SRE, platform engineering, and software roles where reliability is a shared responsibility. I also welcome thoughtful conversations about observability, infrastructure as code, and distributed systems.", emailLabel: "Email", networkLabel: "Professional network", response: "I reply personally. For an initial note, a little context about the challenge and the team is enough.", action: "Email David" },
    footer: "Systems engineering with operational judgement.",
  },
} satisfies Record<Locale, Record<string, unknown>>;
