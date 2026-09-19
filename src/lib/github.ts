export interface PublicRepository {
  archived: boolean;
  description: string | null;
  fork: boolean;
  forksCount: number;
  language: string | null;
  name: string;
  stars: number;
  topics: string[];
  updatedAt: string;
  url: string;
}

interface GitHubRepositoryResponse {
  archived: boolean;
  description: string | null;
  fork: boolean;
  forks_count: number;
  html_url: string;
  language: string | null;
  name: string;
  stargazers_count: number;
  topics: string[];
  updated_at: string;
  visibility: string;
}

const GITHUB_USER = "destaben";
let repositoriesPromise: Promise<PublicRepository[]> | undefined;

export async function getPublicRepositories(): Promise<PublicRepository[]> {
  repositoriesPromise ??= loadPublicRepositories();
  return repositoriesPromise;
}

async function loadPublicRepositories(): Promise<PublicRepository[]> {
  const repositories: PublicRepository[] = [];
  let nextUrl: string | undefined = `https://api.github.com/users/${GITHUB_USER}/repos?per_page=100&sort=updated&direction=desc`;

  while (nextUrl) {
    const response: Response = await fetch(nextUrl, {
      headers: {
        Accept: "application/vnd.github+json",
        "User-Agent": "info.destaben.dev",
        ...(process.env.GITHUB_TOKEN
          ? { Authorization: `Bearer ${process.env.GITHUB_TOKEN}` }
          : {}),
      },
    });

    if (!response.ok) {
      throw new Error(`GitHub repository request failed: ${response.status} ${response.statusText}`);
    }

    const page: GitHubRepositoryResponse[] = await response.json();
    repositories.push(
      ...page
        .filter((repository) => repository.visibility === "public")
        .map((repository) => ({
          archived: repository.archived,
          description: repository.description,
          fork: repository.fork,
          forksCount: repository.forks_count,
          language: repository.language,
          name: repository.name,
          stars: repository.stargazers_count,
          topics: repository.topics,
          updatedAt: repository.updated_at,
          url: repository.html_url,
        })),
    );

    nextUrl = response.headers
      .get("link")
      ?.match(/<([^>]+)>; rel="next"/)?.[1];
  }

  return repositories;
}