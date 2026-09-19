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

export interface MetricsLab extends LabBase {
  kind: "metrics";
  titleLabel: string;
  cpuLabel: string;
  memoryLabel: string;
  servicesLabel: string;
  previousLabel: string;
  nextLabel: string;
  nowLabel: string;
  loadingLabel: string;
  unavailableLabel: string;
  noDataLabel: string;
}

export const profile = {
  name: "David Estaben",
  email: "estaben.sti@gmail.com",
  socialLinks: [
    { label: "GitHub", url: "https://github.com/destaben" },
    { label: "LinkedIn", url: "https://linkedin.com/in/destaben" },
  ],
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
    lab: { label: "Laboratorio", title: "Reticulum explicado desde el recorrido de un mensaje.", copy: "Reticulum es una red resiliente y descentralizada. El recorrido guiado puede crear una identidad temporal para esta prueba y muestra cómo se prepara un mensaje antes de emitirlo." },
    labs: [
      { id: "signal-relay", kind: "relay", title: "Reticulum", summary: "Un punto de contacto Reticulum autohospedado para recibir mensajes desde clientes compatibles.", status: "active", statusLabel: "Activo", technologies: ["Reticulum", "FastAPI"], addressLabel: "Dirección Reticulum", addressPending: "Dirección disponible al publicar el nodo", copyLabel: "Copiar", copiedLabel: "Copiada", checkingLabel: "Comprobando Reticulum", onlineLabel: "Reticulum online", offlineLabel: "Reticulum offline", inboxLabel: "Mensajes recibidos", inboxEmpty: "Todavía no hay mensajes registrados.", inboxNote: "Los mensajes se muestran como texto plano y se conservan de forma limitada.", officialLinkLabel: "Web oficial de Reticulum", wizard: { title: "Recorrido Reticulum", copy: "La identidad temporal se crea sólo al enviar esta prueba. El navegador no recibe claves privadas ni se conecta directamente a Reticulum.", steps: ["Origen temporal", "Destino Reticulum", "Cifrado", "Confirmación"], openLabel: "Explorar recorrido Reticulum", closeLabel: "Cerrar recorrido", sourcePending: "Se crea al enviar la prueba", sourceLabel: "Origen temporal", destinationLabel: "Destino de David", messageLabel: "Nota para esta prueba", messagePlaceholder: "Escribe un mensaje breve", sendLabel: "Enviar prueba", preparingLabel: "Preparando sesión segura", unavailableLabel: "El envío educativo no está habilitado en este nodo.", queuedLabel: "Mensaje en cola", deliveredLabel: "Entrega confirmada", failedLabel: "No se pudo entregar", routeWaitingLabel: "Pendiente", routeSourceReadyLabel: "Identidad temporal preparada", routeEncryptedLabel: "Mensaje cifrado por Reticulum", routeRoutingLabel: "Esperando acuse de la ruta", routeReceivedLabel: "Recibido por Reticulum", routeConfirmedLabel: "Acuse de Reticulum confirmado", routeDeliveryFailedLabel: "El destino no confirmó la entrega", routeOutboundFailedLabel: "El nodo no pudo emitir el mensaje", routeUnknownFailedLabel: "La entrega terminó con un error", telegramLabel: "Aviso Telegram", telegramConfiguredLabel: "Telegram configurado", telegramUnavailableLabel: "Telegram no configurado", telegramCopy: "Cuando Reticulum recibe el mensaje, puede enviar un aviso privado por Telegram." } },
      { id: "container-metrics", kind: "metrics", title: "cAdvisor", summary: "Uso de CPU y memoria de los servicios de mi servidor personal, consultado a través de Prometheus.", status: "active", statusLabel: "En directo", technologies: ["cAdvisor", "Prometheus"], titleLabel: "Métricas de contenedores", cpuLabel: "CPU", memoryLabel: "Memoria", servicesLabel: "Servicios", previousLabel: "Intervalo anterior", nextLabel: "Intervalo siguiente", nowLabel: "Volver a ahora", loadingLabel: "Cargando métricas", unavailableLabel: "Las métricas no están disponibles ahora.", noDataLabel: "No hay muestras en este intervalo." },
    ] satisfies (RelayLab | MetricsLab)[],
    experience: { label: "Trayectoria", title: "Experiencia en software, cloud y operaciones.", items: [
      { period: "2021 - hoy", role: "Software Developer / SRE", company: "adidas", focus: "Observabilidad, automatización y orquestación." },
      { period: "2020 - 2021", role: "Cloud Engineer", company: "NTT Data", focus: "Infraestructura, optimización de costes e integración." },
      { period: "2017 - 2020", role: "DevOps Engineer / Software Developer", company: "Darecode, Network Solutions Control y A&T Ingeniería", focus: "Operación, mantenimiento y desarrollo de software." },
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
    lab: { label: "Lab", title: "Reticulum explained through a message journey.", copy: "Reticulum is a resilient, decentralised network. The guided journey can create a temporary identity for this test and shows how a message is prepared before it is emitted." },
    labs: [
      { id: "signal-relay", kind: "relay", title: "Reticulum", summary: "A self-hosted Reticulum contact point for receiving messages from compatible clients.", status: "active", statusLabel: "Active", technologies: ["Reticulum", "FastAPI"], addressLabel: "Reticulum address", addressPending: "Address available once the node is published", copyLabel: "Copy", copiedLabel: "Copied", checkingLabel: "Checking Reticulum", onlineLabel: "Reticulum online", offlineLabel: "Reticulum offline", inboxLabel: "Received messages", inboxEmpty: "No messages have been recorded yet.", inboxNote: "Messages are shown as plain text and retained for a limited time.", officialLinkLabel: "Reticulum official website", wizard: { title: "Reticulum journey", copy: "The temporary identity is created only when this test is sent. The browser never receives private keys or connects directly to Reticulum.", steps: ["Temporary source", "Reticulum destination", "Encryption", "Confirmation"], openLabel: "Explore the Reticulum journey", closeLabel: "Close journey", sourcePending: "Created when the test is sent", sourceLabel: "Temporary source", destinationLabel: "David's destination", messageLabel: "Note for this test", messagePlaceholder: "Write a short message", sendLabel: "Send test", preparingLabel: "Preparing secure session", unavailableLabel: "Educational sending is not enabled on this node.", queuedLabel: "Message queued", deliveredLabel: "Delivery confirmed", failedLabel: "Delivery failed", routeWaitingLabel: "Waiting", routeSourceReadyLabel: "Temporary identity prepared", routeEncryptedLabel: "Message encrypted by Reticulum", routeRoutingLabel: "Waiting for route acknowledgement", routeReceivedLabel: "Received by Reticulum", routeConfirmedLabel: "Reticulum acknowledgement confirmed", routeDeliveryFailedLabel: "The destination did not confirm delivery", routeOutboundFailedLabel: "The node could not emit the message", routeUnknownFailedLabel: "Delivery ended with an error", telegramLabel: "Telegram notice", telegramConfiguredLabel: "Telegram configured", telegramUnavailableLabel: "Telegram not configured", telegramCopy: "When Reticulum receives the message, it can send a private Telegram notification." } },
      { id: "container-metrics", kind: "metrics", title: "cAdvisor", summary: "CPU and memory use from my personal server services, queried through Prometheus.", status: "active", statusLabel: "Live", technologies: ["cAdvisor", "Prometheus"], titleLabel: "Container metrics", cpuLabel: "CPU", memoryLabel: "Memory", servicesLabel: "Services", previousLabel: "Previous interval", nextLabel: "Next interval", nowLabel: "Back to now", loadingLabel: "Loading metrics", unavailableLabel: "Metrics are unavailable right now.", noDataLabel: "There are no samples in this interval." },
    ] satisfies (RelayLab | MetricsLab)[],
    experience: { label: "Experience", title: "Experience across software, cloud, and operations.", items: [
      { period: "2021 - present", role: "Software Developer / SRE", company: "adidas", focus: "Observability, automation, and orchestration." },
      { period: "2020 - 2021", role: "Cloud Engineer", company: "NTT Data", focus: "Infrastructure, cost optimisation, and integration." },
      { period: "2017 - 2020", role: "DevOps Engineer / Software Developer", company: "Darecode, Network Solutions Control, and A&T Ingeniería", focus: "Operations, maintenance, and software development." },
    ] },
    contact: { label: "Contact", title: "A good conversation can start with a difficult problem.", copy: "I am interested in SRE, platform engineering, and software roles where reliability is a shared responsibility. I also welcome thoughtful conversations about observability, infrastructure as code, and distributed systems.", emailLabel: "Email", networkLabel: "Professional network", response: "I reply personally. For an initial note, a little context about the challenge and the team is enough.", action: "Email David" },
    footer: "Systems engineering with operational judgement.",
  },
} satisfies Record<Locale, Record<string, unknown>>;
