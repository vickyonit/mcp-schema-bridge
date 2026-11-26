/** Error hierarchy. Every error carries the JSON Pointer of the offending location. */
export class SchemaBridgeError extends Error {
  readonly pointer: string;
  readonly detail: string;
  constructor(message: string, pointer = "") {
    super(`${message} (at ${pointer || "/"})`);
    this.name = new.target.name;
    this.detail = message;
    this.pointer = pointer;
  }
}
export class InvalidInputError extends SchemaBridgeError {}
export class UnsupportedSchemaError extends SchemaBridgeError {}
export class LimitExceededError extends SchemaBridgeError {}
export class ReverseMismatchError extends SchemaBridgeError {}
