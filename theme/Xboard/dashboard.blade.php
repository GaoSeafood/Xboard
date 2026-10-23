@php
  $themeAssetRoot = "/theme/{$theme}/assets/ez-theme";
  $manifestPath = public_path("theme/{$theme}/assets/ez-theme/.vite/manifest.json");
  $manifest = is_file($manifestPath) ? json_decode(file_get_contents($manifestPath), true) : [];
  $entry = $manifest['index.html'] ?? null;
  $themeStyles = [];
  $themeModulePreloads = [];
  $visitedManifestEntries = [];
  $collectEntryAssets = function ($key) use (&$collectEntryAssets, &$themeStyles, &$themeModulePreloads, &$visitedManifestEntries, $manifest) {
    if (!isset($manifest[$key]) || in_array($key, $visitedManifestEntries, true)) {
      return;
    }
    $visitedManifestEntries[] = $key;
    foreach (($manifest[$key]['imports'] ?? []) as $import) {
      $collectEntryAssets($import);
    }
    foreach (($manifest[$key]['css'] ?? []) as $css) {
      if (!in_array($css, $themeStyles, true)) {
        $themeStyles[] = $css;
      }
    }
    if (!empty($manifest[$key]['file']) && !in_array($manifest[$key]['file'], $themeModulePreloads, true)) {
      $themeModulePreloads[] = $manifest[$key]['file'];
    }
  };
  if ($entry) {
    foreach (($entry['imports'] ?? []) as $import) {
      $collectEntryAssets($import);
    }
    foreach (($entry['css'] ?? []) as $css) {
      if (!in_array($css, $themeStyles, true)) {
        $themeStyles[] = $css;
      }
    }
  }
@endphp
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,minimum-scale=1,user-scalable=no" />
  <meta name="theme-color" content="#F4F7FB" />
  <meta name="description" content="筋斗云用户中心" />
  <title>筋斗云</title>
  <link rel="icon" type="image/png" href="/theme/{{$theme}}/assets/brand/jindouyun-mijiu-logo-32.png" />
  @foreach ($themeModulePreloads as $module)
    <link rel="modulepreload" crossorigin href="{{ $themeAssetRoot }}/{{ $module }}" />
  @endforeach
  @foreach ($themeStyles as $css)
    <link rel="stylesheet" href="{{ $themeAssetRoot }}/{{ $css }}" />
  @endforeach
  <link rel="stylesheet" href="/theme/{{$theme}}/assets/brand/jindouyun.css?v=20261021" />
</head>
<body>
  <div id="app"></div>
  @if ($entry)
    <script type="module" crossorigin src="{{ $themeAssetRoot }}/{{ $entry['file'] }}"></script>
  @endif
  {!! $theme_config['custom_html'] !!}
</body>
</html>
