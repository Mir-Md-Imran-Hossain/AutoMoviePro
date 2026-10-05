<?php
require __DIR__ . '/includes/bootstrap.php';
require_once __DIR__ . '/includes/agent_llm.php';
$system = amp_agent_system_prompt('bn', 2998, 499);
$out = amp_agent_chat_llm($config, $system, [
    ['role' => 'user', 'content' => 'দাম কত? সংক্ষেপে বাংলায় বলো।'],
]);
echo $out === null ? "LLM_FAIL\n" : ("LLM_OK\n" . $out . "\n");

$systemHi = amp_agent_system_prompt('hi', 2998, 499);
$out2 = amp_agent_chat_llm($config, $systemHi, [
    ['role' => 'user', 'content' => 'कीमत क्या है? केवल हिंदी में।'],
]);
echo $out2 === null ? "HI_FAIL\n" : ("HI_OK\n" . mb_substr($out2, 0, 250) . "\n");
