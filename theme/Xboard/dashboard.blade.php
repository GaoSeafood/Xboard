<!doctype html>
<html lang="zh-CN">

<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,minimum-scale=1,user-scalable=no" />
  <title>筋斗云</title>
  <meta name="theme-color" content="#F4F7FB" />
  <link rel="icon" type="image/png" href="/theme/{{$theme}}/assets/brand/jindouyun-mijiu-logo-32.png" />
  <link rel="stylesheet" href="/theme/{{$theme}}/assets/brand/jindouyun.css?v=20261021" />
  <script type="module" crossorigin src="/theme/{{$theme}}/assets/umi.js"></script>
</head>

<body>

  <script>
    window.routerBase = "/";
    window.settings = {
      title: '筋斗云',
      assets_path: '/theme/{{$theme}}/assets',
      theme: {
        color: '{{ $theme_config['theme_color'] ?? "default" }}',
      },
      version: '{{$version}}',
      background_url: '{{$theme_config['background_url']}}',
      description: '筋斗云',
      i18n: [
        'zh-CN',
        'en-US',
        'ja-JP',
        'vi-VN',
        'ko-KR',
        'zh-TW',
        'fa-IR'
      ],
      logo: '/theme/{{$theme}}/assets/brand/jindouyun-mijiu-logo-512.webp'
    }
  </script>
  <script src="/theme/{{$theme}}/assets/brand/jindouyun-brand.js?v=20261021"></script>
  <div id="app"></div>
  {!! $theme_config['custom_html'] !!}
</body>

</html>
