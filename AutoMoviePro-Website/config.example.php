<?php
/**
 * AutoMovie Pro — copy this file to config.php and fill DB credentials.
 * Do not upload config.example.php secrets; config.php stays on server only.
 */
return [
    'db_host' => 'localhost',
    'db_name' => 'automoviepro',
    'db_user' => 'db_username',
    'db_pass' => 'db_password',
    'db_charset' => 'utf8mb4',

    'site_url' => 'https://automoviepro.com',
    'site_name' => 'AutoMovie Pro',

    'download_url' => 'https://automoviepro.com/downloads/AutoMoviePro-Setup.exe',
    'install_guide_url' => 'https://automoviepro.com/guide.html',

    // WhatsApp Business Cloud API (optional — leave empty to log only)
    'whatsapp_token' => '',
    'whatsapp_phone_id' => '',
    'whatsapp_admin_number' => '8801684355055',

    // API token lifetime (days)
    'api_token_days' => 30,

    'timezone' => 'Asia/Dhaka',
];
