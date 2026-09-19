import rss from "@astrojs/rss";
import { getCollection, type CollectionEntry } from "astro:content";
import { site } from "../config/site";

export async function GET(context: { site: URL | undefined }) {
  const posts: CollectionEntry<"blog">[] = await getCollection("blog");
  const publishedPosts = posts.filter((post) => !post.data.draft);
  const postLink = (post: CollectionEntry<"blog">) => {
    const slug = post.id.split("/").at(-1);
    const prefix = post.data.locale === "es" ? "/es/bitacora" : "/en/notes";
    return `${prefix}/${slug}/`;
  };

  return rss({
    title: site.title,
    description: site.description,
    site: context.site ?? site.url,
    items: publishedPosts.map((post) => ({
      title: post.data.title,
      description: post.data.description,
      pubDate: post.data.pubDate,
      link: postLink(post),
    })),
  });
}