export const profile = {
  name: "David Estabén",
  role: "Site Reliability Engineer",
  company: "Adidas",
  companyUrl: "https://www.adidas.co.uk",
  location: "Zaragoza, Spain",
  email: "estaben.sti@gmail.com",
  image: "/images/author/profile.jpg",
  summary:
    "I turn operational processes into dependable code and infrastructure. My work focuses on making systems observable, repeatable, and easier for teams to run.",
  socialLinks: [
    { label: "GitHub", url: "https://github.com/destaben" },
    { label: "LinkedIn", url: "https://linkedin.com/in/destaben" },
  ],
};

export const skills = [
  { name: "Kubernetes", image: "/images/sections/skills/kubernetes.png", url: "https://kubernetes.io/", summary: "Deployment, operations, controllers, and production troubleshooting." },
  { name: "Python", image: "/images/sections/skills/python.png", url: "https://www.python.org/", summary: "Scalable, testable, and maintainable software for operations." },
  { name: "Cloud", image: "/images/sections/skills/cloud.png", summary: "Hands-on experience across GCP, AWS, Azure, and Oracle Cloud." },
  { name: "Docker", image: "/images/sections/skills/docker.svg", url: "https://www.docker.com/", summary: "Containerized workloads, multi-stage builds, and multi-architecture images." },
  { name: "Prometheus", image: "/images/sections/skills/prometheus.png", url: "https://prometheus.io/", summary: "Metrics, PromQL, Alertmanager, and exporter development." },
  { name: "Linux", image: "/images/sections/skills/linux.png", summary: "Daily driver with shell scripting and systems administration." },
  { name: "Git", image: "/images/sections/skills/git.png", url: "https://git-scm.com/", summary: "Git-based delivery workflows with GitHub and GitLab." },
  { name: "Terraform", image: "/images/sections/skills/terraform.png", summary: "Infrastructure as code, troubleshooting, security, and review." },
];

export const experience = [
  { company: "Adidas", url: "https://www.adidas.co.uk", location: "Zaragoza", role: "Software Developer - SRE", period: "Apr 2021 - Present", overview: "Europe's largest sportswear manufacturer and the world's second largest.", responsibilities: ["Observability", "Automation", "Orchestration"] },
  { company: "NTT Data", url: "https://uk.nttdata.com", location: "Zaragoza", role: "Cloud Engineer", period: "May 2020 - Apr 2021", overview: "Global IT services and consulting company headquartered in Tokyo.", responsibilities: ["Infrastructure", "Cost optimization", "Integration"] },
  { company: "Darecode", url: "https://darecode.com/", location: "Zaragoza", role: "Senior DevOps Engineer", period: "Jan 2019 - Apr 2020", overview: "Spanish technology services company headquartered in Zaragoza.", responsibilities: ["Operations", "Observability", "Maintenance"] },
  { company: "Network Solutions Control", url: "https://www.nscontrol.es/", location: "Zaragoza", role: "DevOps Engineer - Software Developer", period: "Apr 2018 - Jan 2019", overview: "Spanish technology services company headquartered in Madrid.", responsibilities: ["Web development", "DevOps", "Maintenance"] },
  { company: "A&T Ingeniería", url: "https://atingenieria.net", location: "Zaragoza", role: "Planner - Software Developer", period: "Jul 2017 - Feb 2018", overview: "Spanish engineering services company headquartered in Zaragoza.", responsibilities: ["Software development", "FTTH", "Maintenance"] },
];

export const education = [
  { institution: "Official Language School", qualification: "B2 English", period: "2020 - Present" },
  { institution: "IES Tiempos Modernos", qualification: "Technician in Telecommunication Systems and IT", period: "2009 - 2011" },
];
