# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)

<!--
## [<exact release including patch>](<github compare url>) - <release date in YYYY-MM-DD>
### Added
  - <summary of new features>

### Changed
  - <for changes in existing functionality>

### Deprecated
  - <for soon-to-be removed features>

### Removed
  - <for now removed features>

### Fixed
  - <for any bug fixes>

### Security
  - <in case of vulnerabilities>
-->

## [Unreleased](https://github.com/cyverse/chromogenic/compare/0.5.1...HEAD) - YYYY-MM-DD

## [0.5.1](https://github.com/cyverse/chromogenic/compare/0.5.0...0.5.1) - 2019-06-07
### Fixed
  - Check for '<name>cloud-init</name>' to make sure 'cloud-init' is installed
    ([#15](https://github.com/cyverse/chromogenic/pull/15))

## [0.5.0](https://github.com/cyverse/chromogenic/compare/0.4.20...0.5.0) - 2019-06-03
  - Replace chroot and mount with virt-sysprep for preparing and cleaning images
    ([#14](https://github.com/cyverse/chromogenic/pull/14))

## [0.4.20](https://github.com/cyverse/chromogenic/compare/0.4.19...0.4.20) - 2018-09-14
### Fixed
  - Fix unnecessary expensive Nova API call when only one server is needed
    ([#11](https://github.com/cyverse/chromogenic/pull/11))

## [0.4.19](https://github.com/cyverse/chromogenic/compare/0.4.18...0.4.19) - 2018-08-31
### Added
  - Added PR template, change log, and travis to automatically push new pypi
    releases when tags are pushed
    ([#9](https://github.com/cyverse/chromogenic/pull/9))

### Fixed
  - Fix imaging broken on linux 4.4.0 kernels
    ([#8](https://github.com/cyverse/chromogenic/pull/8))

## [0.4.18](https://github.com/cyverse/chromogenic/compare/0.4.17...0.4.18) - 2018-05-18
### Fixed
  - Fix cache issue causing imaging to fail
    ([#7](https://github.com/cyverse/chromogenic/pull/7))
