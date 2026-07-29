// errors.ts — 回测引擎分层错误类型
// 每种错误携带错误码和上下文，便于上层精确诊断和展示

/** 错误码枚举 */
export enum BacktestErrorCode {
  /** 数据相关错误（K线为空、数据缺失、格式错误） */
  DATA_EMPTY = 'DATA_EMPTY',
  DATA_INVALID = 'DATA_INVALID',
  DATA_INSUFFICIENT = 'DATA_INSUFFICIENT',
  /** 指标计算错误 */
  INDICATOR_CALC_FAILED = 'INDICATOR_CALC_FAILED',
  /** 信号生成错误 */
  SIGNAL_SCRIPT_ERROR = 'SIGNAL_SCRIPT_ERROR',
  SIGNAL_TIMEOUT = 'SIGNAL_TIMEOUT',
  SIGNAL_LENGTH_MISMATCH = 'SIGNAL_LENGTH_MISMATCH',
  /** 参数校验错误 */
  PARAM_INVALID = 'PARAM_INVALID',
  PARAM_OUT_OF_RANGE = 'PARAM_OUT_OF_RANGE',
  /** 运行时错误 */
  RUNTIME_ERROR = 'RUNTIME_ERROR',
}

/** 回测错误基类 */
export class BacktestError extends Error {
  public readonly code: BacktestErrorCode;
  public readonly context: Record<string, unknown>;

  constructor(code: BacktestErrorCode, message: string, context: Record<string, unknown> = {}) {
    super(message);
    this.name = 'BacktestError';
    this.code = code;
    this.context = context;
  }
}

/** 数据错误：K线数据为空、格式非法、数量不足等 */
export class DataError extends BacktestError {
  constructor(code: BacktestErrorCode, message: string, context: Record<string, unknown> = {}) {
    super(code, message, context);
    this.name = 'DataError';
  }
}

/** 指标计算错误：技术指标计算过程中出现异常 */
export class IndicatorError extends BacktestError {
  constructor(code: BacktestErrorCode, message: string, context: Record<string, unknown> = {}) {
    super(code, message, context);
    this.name = 'IndicatorError';
  }
}

/** 信号生成错误：自编指标脚本执行失败、超时、结果长度不匹配等 */
export class SignalError extends BacktestError {
  constructor(code: BacktestErrorCode, message: string, context: Record<string, unknown> = {}) {
    super(code, message, context);
    this.name = 'SignalError';
  }
}

/** 参数校验错误：用户输入参数非法或超出范围 */
export class ParamError extends BacktestError {
  constructor(code: BacktestErrorCode, message: string, context: Record<string, unknown> = {}) {
    super(code, message, context);
    this.name = 'ParamError';
  }
}

/**
 * 判断指定错误是否为致命错误（不可恢复，应中断回测）。
 * 致命错误：DATA_EMPTY、PARAM_INVALID、PARAM_OUT_OF_RANGE
 */
export function isFatalError(error: BacktestError): boolean {
  const fatalCodes: BacktestErrorCode[] = [
    BacktestErrorCode.DATA_EMPTY,
    BacktestErrorCode.PARAM_INVALID,
    BacktestErrorCode.PARAM_OUT_OF_RANGE,
  ];
  return fatalCodes.includes(error.code);
}