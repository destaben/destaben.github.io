export type Locale = "es" | "en";

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
    navigation: [{ label: "Trabajo", href: "#trabajo" }, { label: "Laboratorio", href: "#laboratorio" }, { label: "Trayectoria", href: "#trayectoria" }, { label: "Contacto", href: "#contacto" }],
    archive: { projects: "Proyectos", writing: "Bitácora" },
    hero: { eyebrow: "Ingeniería de fiabilidad y plataformas", title: "Sistemas claros. Equipos seguros.", copy: "Soy Site Reliability Engineer y desarrollador de software. Diseño automatización, observabilidad y plataformas cloud con una idea sencilla: reducir incertidumbre para que los equipos puedan centrarse en entregar valor.", primary: "Ver experiencia", secondary: "Contacto Reticulum" },
    proof: ["SRE y desarrollo de software", "Zaragoza · remoto", "Abierto a oportunidades y colaboración"],
    work: { label: "Áreas de trabajo", title: "Fiabilidad construida desde la práctica.", copy: "Mi trabajo combina visión de producto, criterio operativo y atención al detalle: entender el contexto, eliminar fricción y dejar una base más mantenible.", cases: [
      { number: "01", title: "Sistemas observables", context: "Instrumentación y señales útiles para que los equipos puedan detectar, entender y priorizar problemas con rapidez.", decision: "Convertir datos técnicos en contexto accionable para operación y desarrollo.", tags: ["Observabilidad", "SRE", "Python"] },
      { number: "02", title: "Plataformas que escalan", context: "Entornos de entrega y ejecución que evolucionan sin depender de pasos manuales ni conocimiento aislado.", decision: "Aplicar infraestructura como código, estándares de entrega y automatización que simplifican el cambio.", tags: ["Kubernetes", "Terraform", "CI/CD"] },
      { number: "03", title: "Cloud con criterio", context: "Experiencia en infraestructura, integración y optimización de costes en distintos entornos cloud.", decision: "Equilibrar disponibilidad, seguridad, coste y mantenibilidad en cada decisión técnica.", tags: ["Cloud", "FinOps", "Integración"] },
    ] },
    lab: { label: "Contacto Reticulum", title: "Un canal directo, fuera de las plataformas habituales.", copy: "Cualquiera puede enviar un mensaje a esta dirección LXMF desde un cliente compatible con Reticulum. Cuando llegue, el texto aparecerá aquí junto a la hora de recepción. La identidad del remitente no se publica.", addressLabel: "Dirección LXMF", addressPending: "Dirección disponible al publicar el nodo", copyLabel: "Copiar", copiedLabel: "Copiada", checkingLabel: "Comprobando Signal Relay", onlineLabel: "Signal Relay online", offlineLabel: "Signal Relay offline", inboxLabel: "Mensajes recibidos", inboxEmpty: "Todavía no hay mensajes registrados.", inboxNote: "Los mensajes se muestran como texto plano y se conservan de forma limitada." },
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
    navigation: [{ label: "Work", href: "#work" }, { label: "Lab", href: "#lab" }, { label: "Experience", href: "#experience" }, { label: "Contact", href: "#contact" }],
    archive: { projects: "Projects", writing: "Notes" },
    hero: { eyebrow: "Reliability and platform engineering", title: "Clear systems. Confident teams.", copy: "I am a Site Reliability Engineer and software developer. I build automation, observability, and cloud platforms around one simple idea: reduce uncertainty so teams can focus on delivering value.", primary: "Explore my work", secondary: "Reticulum contact" },
    proof: ["SRE and software engineering", "Zaragoza · remote", "Open to roles and collaboration"],
    work: { label: "Areas of work", title: "Reliability grounded in practice.", copy: "My work brings together product awareness, operational judgement, and care for detail: understand the context, remove friction, and leave a more maintainable foundation.", cases: [
      { number: "01", title: "Observable systems", context: "Instrumentation and useful signals that help teams detect, understand, and prioritise issues quickly.", decision: "Turn technical data into actionable context for operations and development.", tags: ["Observability", "SRE", "Python"] },
      { number: "02", title: "Platforms that scale", context: "Delivery and runtime environments that can evolve without manual steps or isolated knowledge.", decision: "Apply infrastructure as code, delivery standards, and automation that make change easier.", tags: ["Kubernetes", "Terraform", "CI/CD"] },
      { number: "03", title: "Cloud with judgement", context: "Experience across infrastructure, integration, and cost optimisation in varied cloud environments.", decision: "Balance availability, security, cost, and maintainability in every technical decision.", tags: ["Cloud", "FinOps", "Integration"] },
    ] },
    lab: { label: "Reticulum contact", title: "A direct channel beyond the usual platforms.", copy: "Anyone can send a message to this LXMF address from a Reticulum-compatible client. When it arrives, its text appears here with the arrival time. Sender identity is not made public.", addressLabel: "LXMF address", addressPending: "Address available once the node is published", copyLabel: "Copy", copiedLabel: "Copied", checkingLabel: "Checking Signal Relay", onlineLabel: "Signal Relay online", offlineLabel: "Signal Relay offline", inboxLabel: "Received messages", inboxEmpty: "No messages have been recorded yet.", inboxNote: "Messages are shown as plain text and retained for a limited time." },
    experience: { label: "Experience", title: "Experience across software, cloud, and operations.", items: [
      { period: "2021 - present", role: "Software Developer / SRE", company: "adidas", focus: "Observability, automation, and orchestration." },
      { period: "2020 - 2021", role: "Cloud Engineer", company: "NTT Data", focus: "Infrastructure, cost optimisation, and integration." },
      { period: "2017 - 2020", role: "DevOps Engineer / Software Developer", company: "Darecode, Network Solutions Control, and A&T Ingeniería", focus: "Operations, maintenance, and software development." },
    ] },
    contact: { label: "Contact", title: "A good conversation can start with a difficult problem.", copy: "I am interested in SRE, platform engineering, and software roles where reliability is a shared responsibility. I also welcome thoughtful conversations about observability, infrastructure as code, and distributed systems.", emailLabel: "Email", networkLabel: "Professional network", response: "I reply personally. For an initial note, a little context about the challenge and the team is enough.", action: "Email David" },
    footer: "Systems engineering with operational judgement.",
  },
} satisfies Record<Locale, Record<string, unknown>>;
