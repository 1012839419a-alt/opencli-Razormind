import { cli, Strategy } from '@jackwener/opencli/registry';

cli({
  site: 'hn-live-case',
  name: 'top',
  access: 'read',
  description: 'Live Hacker News top stories for the OpenCLI Admin E2E case',
  domain: 'news.ycombinator.com',
  strategy: Strategy.PUBLIC,
  browser: false,
  args: [
    { name: 'limit', type: 'int', default: 3, help: 'Number of live stories' },
  ],
  columns: ['rank', 'id', 'title', 'score', 'author', 'comments', 'url'],
  pipeline: [
    { fetch: { url: 'https://hacker-news.firebaseio.com/v0/topstories.json' } },
    { limit: '${{ Math.min((args.limit ? args.limit : 3) + 5, 20) }}' },
    { map: { id: '${{ item }}' } },
    { fetch: { url: 'https://hacker-news.firebaseio.com/v0/item/${{ item.id }}.json' } },
    { filter: 'item.title && !item.deleted && !item.dead' },
    { map: {
      rank: '${{ index + 1 }}',
      id: '${{ item.id }}',
      title: '${{ item.title }}',
      score: '${{ item.score }}',
      author: '${{ item.by }}',
      comments: '${{ item.descendants }}',
      url: '${{ item.url ? item.url : "https://news.ycombinator.com/item?id=" + item.id }}',
    } },
    { limit: '${{ args.limit }}' },
  ],
});
