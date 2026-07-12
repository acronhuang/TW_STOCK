import { Injectable, Logger } from '@nestjs/common';

/**
 * 技術型態服務 - 12種經典型態識別與計算
 */
@Injectable()
export class TechnicalPatternsService {
  private readonly logger = new Logger(TechnicalPatternsService.name);

  /**
   * 1. W底 (雙底) - 多頭買進信號
   * 計算公式：底部至頸線距離 = 突破後的等幅距離
   */
  detectDoubleBottom(prices: number[], dates: string[]): any {
    const result = {
      pattern: 'W底 (雙底)',
      type: 'bullish',
      signal: '多頭買進信號',
      detected: false,
      neckline: null,
      bottom1: null,
      bottom2: null,
      distance: null,
      target1: null,
      target2: null,
      buyPoint: null,
      stopLoss: null,
      description: '當突破頸線位置後，確立W底型態。頸線突破後不能再跌破，是「大賺小賠」的波段操作。',
    };

    if (prices.length < 20) return result;

    // 找尋兩個低點
    const bottoms = this.findLocalMinima(prices, 5);
    if (bottoms.length < 2) return result;

    // 取最近的兩個低點
    const bottom1Idx = bottoms[bottoms.length - 2];
    const bottom2Idx = bottoms[bottoms.length - 1];
    
    const bottom1Price = prices[bottom1Idx];
    const bottom2Price = prices[bottom2Idx];
    
    // 雙底價格差異不超過 3%
    if (Math.abs(bottom1Price - bottom2Price) / bottom1Price > 0.03) {
      return result;
    }

    // 找頸線（兩個底之間的高點）
    const midHigh = this.findMaxBetween(prices, bottom1Idx, bottom2Idx);
    const neckline = prices[midHigh];
    
    // 計算目標價
    const distance = neckline - Math.min(bottom1Price, bottom2Price);
    const target1 = neckline + distance;
    const target2 = neckline + distance * 2;
    
    // 檢查是否突破頸線
    const currentPrice = prices[prices.length - 1];
    const detected = currentPrice > neckline * 1.02; // 突破需要超過2%

    result.detected = detected;
    result.neckline = neckline;
    result.bottom1 = { index: bottom1Idx, price: bottom1Price, date: dates[bottom1Idx] };
    result.bottom2 = { index: bottom2Idx, price: bottom2Price, date: dates[bottom2Idx] };
    result.distance = distance;
    result.target1 = target1;
    result.target2 = target2;
    result.buyPoint = neckline * 1.02;
    result.stopLoss = Math.min(bottom1Price, bottom2Price) * 0.97;

    if (detected) {
      const potentialGain = ((target1 - currentPrice) / currentPrice * 100).toFixed(2);
      result.description += ` 第一目標價: ${target1.toFixed(2)}，第二目標價: ${target2.toFixed(2)}。潛在獲利: ${potentialGain}%`;
    }

    return result;
  }

  /**
   * 2. 破底翻 - 多頭買進信號（含主力甩轎動作）
   */
  detectFalseBreakdown(prices: number[], dates: string[]): any {
    const result = {
      pattern: '破底翻',
      type: 'bullish',
      signal: '多頭買進信號',
      detected: false,
      supportLevel: null,
      breakdownPrice: null,
      recoveryPrice: null,
      target: null,
      buyPoint: null,
      description: '築底過程中跌破支撐後翻升站回頸線。含「甩轎」動作，表示主力在場機率高。',
    };

    if (prices.length < 15) return result;

    // 找支撐位（近期低點區域）
    const recentLows = prices.slice(-30, -5);
    const supportLevel = Math.min(...recentLows);
    
    // 檢查是否有跌破後快速拉回
    for (let i = prices.length - 10; i < prices.length - 2; i++) {
      if (prices[i] < supportLevel * 0.98) { // 跌破支撐
        const breakdownPrice = prices[i];
        const recoveryIndex = i + 1;
        
        // 檢查後續是否拉回站上支撐
        if (prices[recoveryIndex] > supportLevel && prices[prices.length - 1] > supportLevel * 1.02) {
          result.detected = true;
          result.supportLevel = supportLevel;
          result.breakdownPrice = breakdownPrice;
          result.recoveryPrice = prices[recoveryIndex];
          result.buyPoint = supportLevel * 1.02;
          
          // 計算目標價（使用20%作為預期漲幅）
          result.target = prices[prices.length - 1] * 1.20;
          
          result.description += ` 支撐位: ${supportLevel.toFixed(2)}，跌破點: ${breakdownPrice.toFixed(2)}，目標價: ${result.target.toFixed(2)}`;
          break;
        }
      }
    }

    return result;
  }

  /**
   * 3. 破底翻 (W底) - 更安全的底部布局
   */
  detectDoubleBottomWithFalseBreakdown(prices: number[], dates: string[]): any {
    const wBottom = this.detectDoubleBottom(prices, dates);
    const falseBreakdown = this.detectFalseBreakdown(prices, dates);
    
    const result = {
      pattern: '破底翻 (W底)',
      type: 'bullish',
      signal: '多頭買進信號',
      detected: wBottom.detected && falseBreakdown.detected,
      wBottomData: wBottom,
      falseBreakdownData: falseBreakdown,
      description: 'W底第二隻腳破底後拉回，是更進階安全的底部布局。等待時間越長獲利空間越大。',
    };

    return result;
  }

  /**
   * 4. 下飄旗形 - 多頭中繼型態
   */
  detectBullishFlag(prices: number[], dates: string[]): any {
    const result = {
      pattern: '下飄旗形',
      type: 'bullish',
      signal: '多頭中繼信號',
      detected: false,
      trendStart: null,
      trendGain: null,
      flagHigh: null,
      flagLow: null,
      target: null,
      description: '上漲途中的向下整理，突破上緣頸線為再度攻擊信號。',
    };

    if (prices.length < 30) return result;

    // 找出前期上漲趨勢
    const trendStartIdx = prices.length - 30;
    const flagStartIdx = prices.length - 15;
    
    const trendStart = prices[trendStartIdx];
    const trendPeak = Math.max(...prices.slice(trendStartIdx, flagStartIdx));
    const trendGain = trendPeak - trendStart;
    
    // 檢查是否有明顯上漲（至少20%）
    if (trendGain / trendStart < 0.15) return result;
    
    // 檢查整理區間（下飄旗形）
    const flagPrices = prices.slice(flagStartIdx);
    const flagHigh = Math.max(...flagPrices.slice(0, -3));
    const flagLow = Math.min(...flagPrices.slice(0, -3));
    const flagRange = (flagHigh - flagLow) / flagHigh;
    
    // 整理區間幅度應該較小（5-15%）
    if (flagRange < 0.05 || flagRange > 0.20) return result;
    
    // 檢查是否突破旗形上緣
    const currentPrice = prices[prices.length - 1];
    const breakout = currentPrice > flagHigh * 1.02;
    
    result.detected = breakout;
    result.trendStart = { price: trendStart, gain: trendGain, gainPercent: (trendGain / trendStart * 100).toFixed(2) };
    result.trendGain = trendGain;
    result.flagHigh = flagHigh;
    result.flagLow = flagLow;
    result.target = flagHigh + trendGain;
    
    if (breakout) {
      const potentialGain = ((result.target - currentPrice) / currentPrice * 100).toFixed(2);
      result.description += ` 前期漲幅: ${result.trendStart.gainPercent}%，目標價: ${result.target.toFixed(2)}，潛在獲利: ${potentialGain}%`;
    }

    return result;
  }

  /**
   * 5. 上飄旗形 - 空頭中繼型態
   */
  detectBearishFlag(prices: number[], dates: string[]): any {
    const result = {
      pattern: '上飄旗形',
      type: 'bearish',
      signal: '空頭中繼信號',
      detected: false,
      trendStart: null,
      trendLoss: null,
      flagHigh: null,
      flagLow: null,
      target: null,
      description: '下跌途中的向上整理，跌破下緣頸線為空頭再度攻擊。',
    };

    if (prices.length < 30) return result;

    // 找出前期下跌趨勢
    const trendStartIdx = prices.length - 30;
    const flagStartIdx = prices.length - 15;
    
    const trendStart = prices[trendStartIdx];
    const trendLow = Math.min(...prices.slice(trendStartIdx, flagStartIdx));
    const trendLoss = trendStart - trendLow;
    
    // 檢查是否有明顯下跌（至少15%）
    if (trendLoss / trendStart < 0.15) return result;
    
    // 檢查整理區間（上飄旗形）
    const flagPrices = prices.slice(flagStartIdx);
    const flagHigh = Math.max(...flagPrices.slice(0, -3));
    const flagLow = Math.min(...flagPrices.slice(0, -3));
    
    // 檢查是否跌破旗形下緣
    const currentPrice = prices[prices.length - 1];
    const breakdown = currentPrice < flagLow * 0.98;
    
    result.detected = breakdown;
    result.trendStart = { price: trendStart, loss: trendLoss, lossPercent: (trendLoss / trendStart * 100).toFixed(2) };
    result.trendLoss = trendLoss;
    result.flagHigh = flagHigh;
    result.flagLow = flagLow;
    result.target = flagLow - trendLoss;
    
    if (breakdown) {
      const potentialLoss = ((currentPrice - result.target) / currentPrice * 100).toFixed(2);
      result.description += ` 前期跌幅: ${result.trendStart.lossPercent}%，目標價: ${result.target.toFixed(2)}，避免損失: ${potentialLoss}%`;
    }

    return result;
  }

  /**
   * 6. M頭 (雙頂) - 空單進場信號
   */
  detectDoubleTop(prices: number[], dates: string[]): any {
    const result = {
      pattern: 'M頭 (雙頂)',
      type: 'bearish',
      signal: '空單進場信號',
      detected: false,
      neckline: null,
      top1: null,
      top2: null,
      distance: null,
      target1: null,
      target2: null,
      sellPoint: null,
      description: 'W底的反向。跌破頸線後不能再站回。',
    };

    if (prices.length < 20) return result;

    // 找尋兩個高點
    const tops = this.findLocalMaxima(prices, 5);
    if (tops.length < 2) return result;

    // 取最近的兩個高點
    const top1Idx = tops[tops.length - 2];
    const top2Idx = tops[tops.length - 1];
    
    const top1Price = prices[top1Idx];
    const top2Price = prices[top2Idx];
    
    // 雙頂價格差異不超過 3%
    if (Math.abs(top1Price - top2Price) / top1Price > 0.03) {
      return result;
    }

    // 找頸線（兩個頂之間的低點）
    const midLow = this.findMinBetween(prices, top1Idx, top2Idx);
    const neckline = prices[midLow];
    
    // 計算目標價
    const distance = Math.max(top1Price, top2Price) - neckline;
    const target1 = neckline - distance;
    const target2 = neckline - distance * 2;
    
    // 檢查是否跌破頸線
    const currentPrice = prices[prices.length - 1];
    const detected = currentPrice < neckline * 0.98;

    result.detected = detected;
    result.neckline = neckline;
    result.top1 = { index: top1Idx, price: top1Price, date: dates[top1Idx] };
    result.top2 = { index: top2Idx, price: top2Price, date: dates[top2Idx] };
    result.distance = distance;
    result.target1 = target1;
    result.target2 = target2;
    result.sellPoint = neckline * 0.98;

    if (detected) {
      const avoidLoss = ((currentPrice - target1) / currentPrice * 100).toFixed(2);
      result.description += ` 第一目標價: ${target1.toFixed(2)}，第二目標價: ${target2.toFixed(2)}。避免損失: ${avoidLoss}%`;
    }

    return result;
  }

  /**
   * 7. 假突破 - 空單進場信號
   */
  detectFalseBreakout(prices: number[], dates: string[]): any {
    const result = {
      pattern: '假突破',
      type: 'bearish',
      signal: '空單進場信號',
      detected: false,
      resistanceLevel: null,
      breakoutPrice: null,
      failedPrice: null,
      target: null,
      description: '股價突破整理區後又跌回頸線之下，屬主力高檔出貨騙線。',
    };

    if (prices.length < 15) return result;

    // 找阻力位（近期高點區域）
    const recentHighs = prices.slice(-30, -5);
    const resistanceLevel = Math.max(...recentHighs);
    
    // 檢查是否有突破後快速回落
    for (let i = prices.length - 10; i < prices.length - 2; i++) {
      if (prices[i] > resistanceLevel * 1.02) { // 突破阻力
        const breakoutPrice = prices[i];
        const failedIndex = i + 1;
        
        // 檢查後續是否跌破阻力位
        if (prices[failedIndex] < resistanceLevel && prices[prices.length - 1] < resistanceLevel * 0.98) {
          result.detected = true;
          result.resistanceLevel = resistanceLevel;
          result.breakoutPrice = breakoutPrice;
          result.failedPrice = prices[failedIndex];
          
          // 計算目標價
          const distance = breakoutPrice - resistanceLevel;
          result.target = resistanceLevel - distance;
          
          const avoidLoss = ((prices[prices.length - 1] - result.target) / prices[prices.length - 1] * 100).toFixed(2);
          result.description += ` 阻力位: ${resistanceLevel.toFixed(2)}，假突破: ${breakoutPrice.toFixed(2)}，目標價: ${result.target.toFixed(2)}，避免損失: ${avoidLoss}%`;
          break;
        }
      }
    }

    return result;
  }

  /**
   * 8. 頭肩頂 - 空單進場信號
   */
  detectHeadAndShoulders(prices: number[], dates: string[]): any {
    const result = {
      pattern: '頭肩頂',
      type: 'bearish',
      signal: '空單進場信號',
      detected: false,
      leftShoulder: null,
      head: null,
      rightShoulder: null,
      neckline: null,
      target: null,
      description: '行情由強轉弱。頭部與頸線距離等於跌破後的等幅跌幅。',
    };

    if (prices.length < 30) return result;

    const peaks = this.findLocalMaxima(prices, 5);
    if (peaks.length < 3) return result;

    // 取最近的三個峰值
    const leftShoulderIdx = peaks[peaks.length - 3];
    const headIdx = peaks[peaks.length - 2];
    const rightShoulderIdx = peaks[peaks.length - 1];
    
    const leftShoulder = prices[leftShoulderIdx];
    const head = prices[headIdx];
    const rightShoulder = prices[rightShoulderIdx];
    
    // 驗證頭肩型態：頭部應該最高，兩肩高度相近
    if (head <= leftShoulder || head <= rightShoulder) return result;
    if (Math.abs(leftShoulder - rightShoulder) / leftShoulder > 0.10) return result;
    
    // 找頸線（左肩和頭之間、頭和右肩之間的低點平均）
    const leftNeck = this.findMinBetween(prices, leftShoulderIdx, headIdx);
    const rightNeck = this.findMinBetween(prices, headIdx, rightShoulderIdx);
    const neckline = (prices[leftNeck] + prices[rightNeck]) / 2;
    
    // 計算目標價
    const distance = head - neckline;
    const target = neckline - distance;
    
    // 檢查是否跌破頸線
    const currentPrice = prices[prices.length - 1];
    const detected = currentPrice < neckline * 0.98;

    result.detected = detected;
    result.leftShoulder = { index: leftShoulderIdx, price: leftShoulder, date: dates[leftShoulderIdx] };
    result.head = { index: headIdx, price: head, date: dates[headIdx] };
    result.rightShoulder = { index: rightShoulderIdx, price: rightShoulder, date: dates[rightShoulderIdx] };
    result.neckline = neckline;
    result.target = target;

    if (detected) {
      const avoidLoss = ((currentPrice - target) / currentPrice * 100).toFixed(2);
      result.description += ` 頭部: ${head.toFixed(2)}，頸線: ${neckline.toFixed(2)}，目標價: ${target.toFixed(2)}，避免損失: ${avoidLoss}%`;
    }

    return result;
  }

  /**
   * 9. 假突破 (頭肩頂) - 空單進場信號
   */
  detectHeadAndShouldersWithFalseBreakout(prices: number[], dates: string[]): any {
    const hns = this.detectHeadAndShoulders(prices, dates);
    const falseBreakout = this.detectFalseBreakout(prices, dates);
    
    const result = {
      pattern: '假突破 (頭肩頂)',
      type: 'bearish',
      signal: '空單進場信號',
      detected: hns.detected || falseBreakout.detected,
      hnsData: hns,
      falseBreakoutData: falseBreakout,
      description: '利用假突破結構，更早判斷高檔轉弱。',
    };

    return result;
  }

  /**
   * 10. 頭肩底 - 多頭買進信號
   */
  detectInverseHeadAndShoulders(prices: number[], dates: string[]): any {
    const result = {
      pattern: '頭肩底',
      type: 'bullish',
      signal: '多頭買進信號',
      detected: false,
      leftShoulder: null,
      head: null,
      rightShoulder: null,
      neckline: null,
      target1: null,
      target2: null,
      description: '底部盤整行情由弱轉強。低點到頸線距離 = 突破後的距離。',
    };

    if (prices.length < 30) return result;

    const troughs = this.findLocalMinima(prices, 5);
    if (troughs.length < 3) return result;

    // 取最近的三個谷值
    const leftShoulderIdx = troughs[troughs.length - 3];
    const headIdx = troughs[troughs.length - 2];
    const rightShoulderIdx = troughs[troughs.length - 1];
    
    const leftShoulder = prices[leftShoulderIdx];
    const head = prices[headIdx];
    const rightShoulder = prices[rightShoulderIdx];
    
    // 驗證頭肩底型態：頭部應該最低，兩肩高度相近
    if (head >= leftShoulder || head >= rightShoulder) return result;
    if (Math.abs(leftShoulder - rightShoulder) / leftShoulder > 0.10) return result;
    
    // 找頸線
    const leftNeck = this.findMaxBetween(prices, leftShoulderIdx, headIdx);
    const rightNeck = this.findMaxBetween(prices, headIdx, rightShoulderIdx);
    const neckline = (prices[leftNeck] + prices[rightNeck]) / 2;
    
    // 計算目標價
    const distance = neckline - head;
    const target1 = neckline + distance;
    const target2 = neckline + distance * 2;
    
    // 檢查是否突破頸線
    const currentPrice = prices[prices.length - 1];
    const detected = currentPrice > neckline * 1.02;

    result.detected = detected;
    result.leftShoulder = { index: leftShoulderIdx, price: leftShoulder, date: dates[leftShoulderIdx] };
    result.head = { index: headIdx, price: head, date: dates[headIdx] };
    result.rightShoulder = { index: rightShoulderIdx, price: rightShoulder, date: dates[rightShoulderIdx] };
    result.neckline = neckline;
    result.target1 = target1;
    result.target2 = target2;

    if (detected) {
      const potentialGain = ((target1 - currentPrice) / currentPrice * 100).toFixed(2);
      result.description += ` 低點: ${head.toFixed(2)}，頸線: ${neckline.toFixed(2)}，目標價: ${target1.toFixed(2)}/${target2.toFixed(2)}，潛在獲利: ${potentialGain}%`;
    }

    return result;
  }

  /**
   * 11. 收斂三角形 (頭部) - 空單進場信號
   */
  detectSymmetricalTriangleTop(prices: number[], dates: string[]): any {
    const result = {
      pattern: '收斂三角形 (頭部)',
      type: 'bearish',
      signal: '空單進場信號',
      detected: false,
      triangleStart: null,
      triangleEnd: null,
      upperTrendline: null,
      lowerTrendline: null,
      breakdownPoint: null,
      target: null,
      description: '需在三角形 1/2 至 3/4 處跌破才有效。',
    };

    if (prices.length < 40) return result;

    const recentPrices = prices.slice(-40);
    const highs = this.findLocalMaxima(recentPrices, 3);
    const lows = this.findLocalMinima(recentPrices, 3);
    
    if (highs.length < 3 || lows.length < 3) return result;
    
    // 檢查高點是否遞減
    const highPrices = highs.map(i => recentPrices[i]);
    const highsDescending = highPrices[0] > highPrices[1] && highPrices[1] > highPrices[2];
    
    // 檢查低點是否遞增
    const lowPrices = lows.map(i => recentPrices[i]);
    const lowsAscending = lowPrices[0] < lowPrices[1] && lowPrices[1] < lowPrices[2];
    
    if (!highsDescending || !lowsAscending) return result;
    
    const triangleStart = recentPrices[0];
    const triangleHeight = highPrices[0] - lowPrices[0];
    const currentPrice = prices[prices.length - 1];
    const lowerTrendline = lowPrices[lowPrices.length - 1];
    
    // 檢查是否在1/2到3/4位置跌破
    const progressRatio = (recentPrices.length - lows[0]) / 40;
    const validBreakdown = progressRatio >= 0.5 && progressRatio <= 0.75;
    
    const detected = currentPrice < lowerTrendline * 0.98 && validBreakdown;
    
    result.detected = detected;
    result.triangleStart = triangleStart;
    result.triangleEnd = currentPrice;
    result.upperTrendline = highPrices[highPrices.length - 1];
    result.lowerTrendline = lowerTrendline;
    result.breakdownPoint = lowerTrendline;
    result.target = lowerTrendline - triangleHeight;

    if (detected) {
      const avoidLoss = ((currentPrice - result.target) / currentPrice * 100).toFixed(2);
      result.description += ` 三角形高度: ${triangleHeight.toFixed(2)}，跌破點: ${lowerTrendline.toFixed(2)}，目標價: ${result.target.toFixed(2)}，避免損失: ${avoidLoss}%`;
    }

    return result;
  }

  /**
   * 12. 收斂三角形 (底部) - 多頭買進信號
   */
  detectSymmetricalTriangleBottom(prices: number[], dates: string[]): any {
    const result = {
      pattern: '收斂三角形 (底部)',
      type: 'bullish',
      signal: '多頭買進信號',
      detected: false,
      triangleStart: null,
      triangleEnd: null,
      upperTrendline: null,
      lowerTrendline: null,
      breakoutPoint: null,
      target1: null,
      target2: null,
      description: '需在三角形 1/2 至 3/4 處突破才有效。',
    };

    if (prices.length < 40) return result;

    const recentPrices = prices.slice(-40);
    const highs = this.findLocalMaxima(recentPrices, 3);
    const lows = this.findLocalMinima(recentPrices, 3);
    
    if (highs.length < 3 || lows.length < 3) return result;
    
    // 檢查高點是否遞減
    const highPrices = highs.map(i => recentPrices[i]);
    const highsDescending = highPrices[0] > highPrices[1] && highPrices[1] > highPrices[2];
    
    // 檢查低點是否遞增
    const lowPrices = lows.map(i => recentPrices[i]);
    const lowsAscending = lowPrices[0] < lowPrices[1] && lowPrices[1] < lowPrices[2];
    
    if (!highsDescending || !lowsAscending) return result;
    
    const triangleStart = recentPrices[0];
    const triangleHeight = highPrices[0] - lowPrices[0];
    const currentPrice = prices[prices.length - 1];
    const upperTrendline = highPrices[highPrices.length - 1];
    
    // 檢查是否在1/2到3/4位置突破
    const progressRatio = (recentPrices.length - highs[0]) / 40;
    const validBreakout = progressRatio >= 0.5 && progressRatio <= 0.75;
    
    const detected = currentPrice > upperTrendline * 1.02 && validBreakout;
    
    result.detected = detected;
    result.triangleStart = triangleStart;
    result.triangleEnd = currentPrice;
    result.upperTrendline = upperTrendline;
    result.lowerTrendline = lowPrices[lowPrices.length - 1];
    result.breakoutPoint = upperTrendline;
    result.target1 = upperTrendline + triangleHeight;
    result.target2 = upperTrendline + triangleHeight * 2;

    if (detected) {
      const potentialGain = ((result.target1 - currentPrice) / currentPrice * 100).toFixed(2);
      result.description += ` 三角形高度: ${triangleHeight.toFixed(2)}，突破點: ${upperTrendline.toFixed(2)}，目標價: ${result.target1.toFixed(2)}/${result.target2.toFixed(2)}，潛在獲利: ${potentialGain}%`;
    }

    return result;
  }

  /**
   * 掃描所有12種型態
   */
  scanAllPatterns(prices: number[], dates: string[]) {
    return {
      timestamp: new Date().toISOString(),
      dataPoints: prices.length,
      patterns: {
        doubleBottom: this.detectDoubleBottom(prices, dates),
        falseBreakdown: this.detectFalseBreakdown(prices, dates),
        doubleBottomWithFalseBreakdown: this.detectDoubleBottomWithFalseBreakdown(prices, dates),
        bullishFlag: this.detectBullishFlag(prices, dates),
        bearishFlag: this.detectBearishFlag(prices, dates),
        doubleTop: this.detectDoubleTop(prices, dates),
        falseBreakout: this.detectFalseBreakout(prices, dates),
        headAndShoulders: this.detectHeadAndShoulders(prices, dates),
        headAndShouldersWithFalseBreakout: this.detectHeadAndShouldersWithFalseBreakout(prices, dates),
        inverseHeadAndShoulders: this.detectInverseHeadAndShoulders(prices, dates),
        symmetricalTriangleTop: this.detectSymmetricalTriangleTop(prices, dates),
        symmetricalTriangleBottom: this.detectSymmetricalTriangleBottom(prices, dates),
      },
      detectedPatterns: [],
    };
  }

  /**
   * 輔助方法：找局部最小值
   */
  private findLocalMinima(prices: number[], window: number): number[] {
    const minima: number[] = [];
    for (let i = window; i < prices.length - window; i++) {
      let isMinimum = true;
      for (let j = i - window; j <= i + window; j++) {
        if (j !== i && prices[j] <= prices[i]) {
          isMinimum = false;
          break;
        }
      }
      if (isMinimum) {
        minima.push(i);
      }
    }
    return minima;
  }

  /**
   * 輔助方法：找局部最大值
   */
  private findLocalMaxima(prices: number[], window: number): number[] {
    const maxima: number[] = [];
    for (let i = window; i < prices.length - window; i++) {
      let isMaximum = true;
      for (let j = i - window; j <= i + window; j++) {
        if (j !== i && prices[j] >= prices[i]) {
          isMaximum = false;
          break;
        }
      }
      if (isMaximum) {
        maxima.push(i);
      }
    }
    return maxima;
  }

  /**
   * 輔助方法：找區間最大值索引
   */
  private findMaxBetween(prices: number[], start: number, end: number): number {
    let maxIdx = start;
    let maxPrice = prices[start];
    for (let i = start + 1; i <= end; i++) {
      if (prices[i] > maxPrice) {
        maxPrice = prices[i];
        maxIdx = i;
      }
    }
    return maxIdx;
  }

  /**
   * 輔助方法：找區間最小值索引
   */
  private findMinBetween(prices: number[], start: number, end: number): number {
    let minIdx = start;
    let minPrice = prices[start];
    for (let i = start + 1; i <= end; i++) {
      if (prices[i] < minPrice) {
        minPrice = prices[i];
        minIdx = i;
      }
    }
    return minIdx;
  }
}
