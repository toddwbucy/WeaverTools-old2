//! conforms: analysis-reading-drains-within-a-turn
//!
//! The record's events, drained rather than held, per
//! `weaver-analysis-Spec` section 5.
//!
//! **The drain is the class's rather than the lens's.**
//! `diagnostic-replay-loop` names the diagnostic loop a class with an
//! interchangeable reader, so this module is one drain over a record's
//! events and a reader trait above it: a reader consumes events as they
//! land and holds only what its own reading needs. The lens is the first
//! reader and sets no precedent the next must break.
//!
//! **This unit holds the first half of that assertion and names the second.**
//! The drain hands each line to its reader as it lands and retains none of
//! them, which is what lets a reader hold only what its own reading needs.
//! The bound on what a reading holds, one turn's final layers until the
//! turn's measurement pairs them and the named positions after, is
//! `capture::Streaming`'s, which cites the assertion at that site.
//!
//! A file is a stream that ends, so nothing here is a pipe-only path:
//! every reading takes this road and the sink's shape decides only where
//! the bytes come from.

use std::io::BufRead;

use crate::record::Event;

/// What a reader answers to a drained event.
#[derive(Debug, Clone, PartialEq)]
pub enum Step {
    /// Keep draining.
    Continue,
    /// Stop reading: the reader has what it needs, and the rest of the
    /// stream is someone else's business.
    Done,
    /// The reader refuses, naming why. The drain stops and carries it.
    Refuse(String),
}

/// A reader over a drained record. One method, called per event in
/// landing order. The raw-line hook lets readers account for exact bytes
/// without retaining them, and its default keeps the ordinary event parse.
///
/// **The end of the drain is a reader's second exit**, beside whatever event
/// closes its reading. A record that stops short, from a dead process or a
/// truncated sink, never lands the closing event, so a reader holding a fact
/// it emits only at that event is asked once more when the drain ends,
/// whether the stream ran out or the reader stopped it, and may refuse.
/// The default holds nothing and answers `Continue`.
pub trait Reader {
    fn event(&mut self, event: &Event) -> Step;

    fn line(&mut self, line: &str) -> Step {
        Event::parse(line).map_or(Step::Continue, |event| self.event(&event))
    }

    fn end(&mut self) -> Step {
        Step::Continue
    }
}

/// Why a drain ended.
#[derive(Debug, Clone, PartialEq)]
pub enum Drained {
    /// The stream ended.
    Exhausted,
    /// A reader answered `Done`.
    Stopped,
    /// A reader refused, or the stream failed under it.
    Refused(String),
}

/// Drain a record's lines through a reader. **A malformed line is skipped
/// rather than fatal**, per section 2's reader rules: what a reader does
/// not know it does not read, and a line that is not an event is exactly
/// that.
pub fn drain<R: BufRead>(mut source: R, reader: &mut dyn Reader) -> Drained {
    let mut line = String::new();
    loop {
        line.clear();
        match source.read_line(&mut line) {
            Ok(0) => {
                return match reader.end() {
                    Step::Refuse(why) => Drained::Refused(why),
                    _ => Drained::Exhausted,
                };
            }
            Ok(_) => {}
            Err(error) => return Drained::Refused(format!("the stream failed: {error}")),
        }
        match reader.line(&line) {
            Step::Continue => {}
            Step::Done => {
                return match reader.end() {
                    Step::Refuse(why) => Drained::Refused(why),
                    _ => Drained::Stopped,
                };
            }
            Step::Refuse(why) => return Drained::Refused(why),
        }
    }
}

/// Open a record for draining: a path, or `-` for the standard input. A
/// FIFO opens here exactly as a file does, the blocking open being what
/// pairs the reader with the writer.
pub fn open(path: &str) -> std::io::Result<Box<dyn BufRead>> {
    if path == "-" {
        Ok(Box::new(std::io::BufReader::new(std::io::stdin())))
    } else {
        Ok(Box::new(std::io::BufReader::new(std::fs::File::open(
            path,
        )?)))
    }
}
