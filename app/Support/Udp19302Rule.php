<?php

namespace App\Support;

class Udp19302Rule
{
    public const CLASH = 'AND,((NETWORK,UDP),(DST-PORT,19302)),REJECT';
    public const SURGE = 'AND,((PROTOCOL,UDP),(DEST-PORT,19302)),REJECT';

    public static function clash(array $config): array
    {
        $rules = $config['rules'] ?? [];
        $rules = array_values(array_filter($rules, fn ($rule) => $rule !== self::CLASH));
        array_unshift($rules, self::CLASH);
        $config['rules'] = $rules;
        return $config;
    }

    public static function ini(string $config): string
    {
        $rule = self::SURGE;
        $config = preg_replace('/^\s*' . preg_quote($rule, '/') . '\s*\r?\n/m', '', $config);
        return preg_replace('/^(\[Rule\][ \t]*\r?\n)/mi', '$1' . $rule . "\n", $config, 1);
    }
}
