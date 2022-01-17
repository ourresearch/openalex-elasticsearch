###############################################################################
# json-sanitize-field-names.logstash-filter-ruby.rb
# ---------------------------------
# A script for a Logstash Ruby Filter to transform a JSON string so that the
# resulting JSON string's decoded representation does not contain square
# brackets in keys.
#
# This filter does NOT parse the JSON string into an Object, and has undefined
# behaviour when the string is not valid JSON.
#
#
###############################################################################
#
# Copyright 2020 Ry Biesemeyer
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
def register(params)
  params = params.dup

  # source: the field that contains a JSON string (default: "message")
  @source = params.delete('source') || "message"

  # target: if provided, the target field to place the sanitized result
  #         (default: replace the source in-place)
  @target = params.delete('target') || @source

  # transform: the name of the transformation to apply.
  transform = params.delete('transform') { 'mask_underscore' }
  @replacement = {
    'mask_underscore' => '_',
    'mask_curly'      => '{}',
    'mask_paren'      => '()',
    'strip'           => '',
  }.fetch(transform) { |h,k| report_configuration_error("script_params `transform` must be one of #{h.keys}; got `#{k}`." ) }

  params.empty? || report_configuration_error("unknown value(s) for script_params: #{params.keys}.")
end

def report_configuration_error(message)
  raise LogStash::ConfigurationError, message
end

def filter(event)
  source = event.get(@source)
  return if source.nil?

  fail("expected string") unless source.kind_of?(String)

  result = source.gsub(%r{(?<!\\)"((?:\\"|[^"])+)(?<!\\)"(\s*):}) do |_|
    # $1 is the contents of our quoted key, including any escaped double-quotes
    # $2 is the provided whitespace; we re-attach it to minimize our changes.
    clean_unquoted = $1.tr('[]', @replacement)
    %Q{"#{clean_unquoted}"#{$2}:}
  end

  event.set(@target, result)
rescue => e
  log_meta = {exception: e.message}
  log_meta.update(:backtrace, e.backtrace) if logger.debug?
  logger.error('failed to sanitize field names in JSON', log_meta)
  event.tag('_sanitizejsonfieldnameserror')
ensure
  return [event]
end

test 'defaults' do
  original_message = '{"foo[]":[{"ba[r":"this[0]"}],"ok":"yeah [] woohoo"}'.freeze

  parameters { Hash.new }

  in_event do
    {
      "message" => original_message
    }
  end

  expect("produces single event") do |events|
    events.size == 1
  end

  expect('in-place replaces the square brackets in keys with underscores') do |events|
    event = events.first
    event.include?("message") &&
      event.get("message") == '{"foo__":[{"ba_r":"this[0]"}],"ok":"yeah [] woohoo"}'
  end
end

test '#target' do
  original_message = '{"foo[]":[{"ba[r":"this[0]"}],"ok":"yeah [] woohoo"}'.freeze

  parameters { {"target" => "sanitized_message"} }

  in_event do
    {
      "message" => original_message
    }
  end

  expect("produces single event") do |events|
    events.size == 1
  end

  expect('leaves the original in-tact') do |events|
    event = events.first
    event.include?("message") &&
      event.get("message") == original_message
  end

  expect('sets the target with a sanitized result') do |events|
    event = events.first
    event.include?("sanitized_message") &&
      event.get("sanitized_message") == '{"foo__":[{"ba_r":"this[0]"}],"ok":"yeah [] woohoo"}'
  end
end

test '#source' do
  original_message = '{"foo[]":[{"ba[r":"this[0]"}],"ok":"yeah [] woohoo"}'.freeze

  parameters { {"source" => "json"} }

  in_event do
    {
      "json" => original_message
    }
  end

  expect("produces single event") do |events|
    events.size == 1
  end

  expect('in-place replaces the square brackets in keys with underscores') do |events|
    event = events.first
    event.include?("json") &&
      event.get("json") == '{"foo__":[{"ba_r":"this[0]"}],"ok":"yeah [] woohoo"}'
  end
end

test '#transform(strip)' do
  original_message = '{"foo[]":[{"ba[r":"this[0]"}],"ok":"yeah [] woohoo"}'.freeze

  parameters { {"transform" => "strip", "target" => "sanitized_message" } }

  in_event do
    {
      "message" => original_message
    }
  end

  expect("produces single event") do |events|
    events.size == 1
  end

  expect('sets the target with a sanitized result') do |events|
    event = events.first
    event.include?("sanitized_message") &&
      event.get("sanitized_message") == '{"foo":[{"bar":"this[0]"}],"ok":"yeah [] woohoo"}'
  end
end

test '#transform(mask_curly)' do
  original_message = '{"foo[]":[{"ba[r":"this[0]"}],"ok":"yeah [] woohoo"}'.freeze

  parameters { {"transform" => "mask_curly", "target" => "sanitized_message" } }

  in_event do
    {
      "message" => original_message
    }
  end

  expect("produces single event") do |events|
    events.size == 1
  end

  expect('sets the target with a sanitized result') do |events|
    event = events.first
    event.include?("sanitized_message") &&
      event.get("sanitized_message") == '{"foo{}":[{"ba{r":"this[0]"}],"ok":"yeah [] woohoo"}'
  end
end

test '#transform(mask_paren)' do
  original_message = '{"foo[]":[{"ba[r":"this[0]"}],"ok":"yeah [] woohoo"}'.freeze

  parameters { {"transform" => "mask_paren", "target" => "sanitized_message" } }

  in_event do
    {
      "message" => original_message
    }
  end

  expect("produces single event") do |events|
    events.size == 1
  end

  expect('sets the target with a sanitized result') do |events|
    event = events.first
    event.include?("sanitized_message") &&
      event.get("sanitized_message") == '{"foo()":[{"ba(r":"this[0]"}],"ok":"yeah [] woohoo"}'
  end
end

test "edge-case: value containing string with escaped double-quote followed by a colon" do
  original_message = '{"key[]":"value[]\\":"}'.freeze

  in_event do
    {
      "message" => original_message
    }
  end

  parameters { { "target" => "sanitized_message" } }

  expect("produces single event") do |events|
    events.size == 1
  end

  expect('sets the target with a sanitized result') do |events|
    event = events.first
    event.include?("sanitized_message") &&
      event.get("sanitized_message") == '{"key__":"value[]\\":"}'
  end
end