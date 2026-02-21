[![GitHub Release](https://badgen.net/github/release/warped-pinball/vector/stable)](https://github.com/warped-pinball/vector/releases)
[![License](https://img.shields.io/badge/license-CC%20BY--NC-blue)](https://github.com/warped-pinball/vector/tree/main?tab=License-1-ov-file)
[![GitHub issues](https://img.shields.io/github/issues/warped-pinball/vector)](https://github.com/warped-pinball/vector/issues)
[![GitHub last commit](https://badgen.net/github/last-commit/warped-pinball/vector)](https://github.com/warped-pinball/vector/commits/main)
[![Docs](https://img.shields.io/badge/docs-warpedpinball.com-blue)](https://docs.warpedpinball.com)

# Vector

Vector is a modern hardware and software solution that brings advanced features to classic pinball machines while preserving their original gameplay. It allows your Williams/Bally System 9 and 11 games (with plans for WPC and Data East support in 2025) to take advantage of modern electronics and connectivity.

Check out our [demo site](https://vector.doze.dev) which is hosted on a vector board

Read the docs: [docs.warpedpinball.com](https://docs.warpedpinball.com)

Check us out: [Warped Pinball](https://warpedpinball.com)

Get your Vector: [shop.warpedpinball.com](https://shop.warpedpinball.com)

## Features

- **ZERO subscriptions or dependencies** There are no servers to fail, no services to pay for. You don't even really need to connect to the internet. We don't (and can't) control your device in any way once you purchase it. You may *optionally* install our free updates.
- **WiFi connectivity**: Securely access all the great features of vector from any device on your local internet. There's no "phone-home" or data collection. Don't believe us? You can read the source code right here on GitHub.
- **Adjustments Profiles**: Change your games adjustments / settings through the web interface with a single button click. Save up to 4 profiles so you can easily switch between your "free play", "Tournament", and "Arcade" adjustments, or anything else you like.
- **Live Scores**: Watch scores for in-progress games change in realtime with fun effects.
- **Extended Leaderboard**: Expand the high scores on your machine to 20 slots.
- **Full Player Names**: Register full names for initials so your name shows up on the scoreboard.
- **Personal Leaderboards**: Each registered player gets their own scoreboard with their personal best scores. (This is great for kids who don't make it on the leaderboard!)
- **Tournament Board**: Do you have "the pinball crew" come over to play a tournament and take all the high scores? then enable tournament mode which records every game in chronological order and keeps the scores separate from the standard leaderboard.
- **Initials for System 9**: Williams / Bally System 9 games don't natively support initials on high scores. Vector adds support by allowing users to enter their initials in the web interface after a game.
- **Over-the-Air Updates**: Easily update your Vector with the latest features. Your board will never automatically install software without your permission.
- **API over USB**: Connect directly over USB for API access without requiring network connectivity.
- **Unaltered Gameplay**: Enjoy modern features without changing the classic feel.

## FAQ & Troubleshooting

If you have any questions or trouble we recommend:
 - The bottom of the admin page has helpful documentation
 - [our FAQ video on YouTube](https://youtu.be/iD46myZ2hAI?si=HNcbDbbh4u5xqsF9)
 - [Open an issue](https://github.com/warped-pinball/vector/issues/new/choose)
 - Contact us at [inventingfun@gmail.com](mailto:inventingfun@gmail.com)

## Contributing

We welcome contributions from others. This is a passion project for us and we love sharing that passion with others. In order to run the project you will need our custom hardware but a pinball machine is not strictly required, although highly recommended for "testing" and "breaks" while developing. Reach out if you need any help with your setup.

### Workflow

Generally speaking, development by outside developers should follow this workflow:

1. Open an issue describing what you want.
    It's important to do this since it's entirely possible we've already explored your idea and there's a technical reason we have not implemented it. The constraints within vector are complicated and we work hard to strike a balance between features and performance. So it's a good idea to chat with us first so you can be sure you're working with all the best information.
2. Fork this repository and clone it to your local machine.
3. Set up the development environment (see [dev/readme.md](dev/readme.md))
4. Develop your changes on a new branch.
5. Test your changes on your local machine.
6. Submit a cross-fork pull request to the main branch of this repository.
7. Wait patiently for us to review your changes. We will provide feedback and may ask you to make changes.
8. Once your changes are approved, we will merge them into the main branch and likely make a release soon after.

### Contributors

<a href="https://github.com/warped-pinball/vector/graphs/contributors" alt="Contributors">
  <img src="https://contrib.rocks/image?repo=warped-pinball/vector" />
</a>


## License

This project is licensed under the CC BY-NC License. See the [LICENSE](LICENSE) file for details.
