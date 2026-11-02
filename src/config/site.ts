export const site = {
  title: "David Estabén | Systems & Reliability",
  description:
    "Portfolio of David Estabén, a Site Reliability Engineer focused on observable, repeatable, and resilient systems.",
  url: "https://info.destaben.dev",
  locale: "es",
  image: "/images/site/brand-mark.svg",
};

export interface PageAlternate {
  hreflang: string;
  path: string;
}

export const homeAlternates: readonly PageAlternate[] = [
  { hreflang: "es", path: "/es/" },
  { hreflang: "en", path: "/en/" },
];