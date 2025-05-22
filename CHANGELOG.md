# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.2] - 2025-05-22

### Changed
- Renamed `video_logger.py` to `logger.py` for generic usage
- Enhanced logging with detailed prompt, completion, tokens, and latency tracking
- Added robust step-by-step logging for each phase
- Added `tqdm` dependency for progress visualization
- Improved URL validation logging with `url_valid` flag

### Fixed
- Streamlined logging of validation results
- Fixed cost tracking in asynchronous operations

## [1.3.0] - 2025-05-22

### Added
- Support for video-centric categories via external taxonomy file
- JSON schema validation for awesome list data
- URL validation to ensure all links are reachable
- GitHub stars check for video-related repositories
- Git branch and commit automation
- Markdown to JSON conversion utility
- Enhanced logging with detailed cost and timing information
- Retry logic with exponential back-off for category research
- Asynchronous processing using asyncio for better performance

### Changed
- Improved deduplication with hostname + title matching
- Adjusted fuzzy threshold to 88% for video categories
- Extended CLI with additional flags: --min-results, --time-limit, --global-timeout, --gen-awesome-list, --update
- Added httpx and jsonschema dependencies
- Updated Docker image security with non-root user

### Fixed
- Better error handling with retry logic
- More robust URL validation with HTTP HEAD checks

## [1.2.0] - 2025-04-15

### Added
- Semantic deduplication with embedding similarity
- Comprehensive logging with ISO 8601 timestamps
- Cost ceiling enforcement
- Wall time tracking

## [1.1.0] - 2025-03-10

### Added
- Four-layer deduplication system
- awesome-lint validation
- Dockerfile for containerized execution

## [1.0.0] - 2025-02-01

### Added
- Initial release
- Basic awesome list research functionality
- OpenAI integration
