// 分析数据库中的特殊代码类型
var codes = db.taiwan_stock_info.distinct('stock_id');
var special = {
    etf_6digit: [],
    etf_with_letter: [],
    warrant_t: [],
    other_6digit: [],
    other_with_letter: []
};

codes.forEach(function(code) {
    if (!code) return;
    
    // ETF（已过滤）
    if (code.startsWith('00') && code.length >= 5) {
        if (code.length == 6 && /^\d{6}$/.test(code)) {
            special.etf_6digit.push(code);
        } else if (code.length >= 5 && /^\d{4}[A-Z]/.test(code)) {
            special.etf_with_letter.push(code);
        }
    }
    // 权证（5位数+T）
    else if (/^\d{5}T$/.test(code)) {
        special.warrant_t.push(code);
    }
    // 其他6位数（02开头）
    else if (/^02\d{4}$/.test(code)) {
        special.other_6digit.push(code);
    }
    // 其他字母后缀（非T）
    else if (/^\d{5}[A-Z]$/.test(code) && !code.endsWith('T')) {
        special.other_with_letter.push(code);
    }
});

print('======================================');
print('特殊代码统计：');
print('======================================');
print('ETF (6位数，如 006208):', special.etf_6digit.length, '个');
print('ETF (字母后缀，如 00633L):', special.etf_with_letter.length, '个');
print('权证 (5位数+T，如 01004T):', special.warrant_t.length, '个');
print('其他 (6位数，如 020000):', special.other_6digit.length, '个');
print('其他 (5位数+字母):', special.other_with_letter.length, '个');
print('');
print('💡 建议过滤的代码类型：');
print('   - 权证 (xxxT):', special.warrant_t.length, '个');
print('   - 其他特殊:', special.other_6digit.length + special.other_with_letter.length, '个');
print('');
if (special.warrant_t.length > 0) {
    print('权证示例:', special.warrant_t.slice(0, 10).join(', '));
}
if (special.other_6digit.length > 0) {
    print('其他6位数示例:', special.other_6digit.slice(0, 10).join(', '));
}
if (special.other_with_letter.length > 0) {
    print('其他字母示例:', special.other_with_letter.slice(0, 10).join(', '));
}
