$(function(){
    lpCom.init(this);

    //오브젝트 이벤트 활당
    if(typeof(fnSetObjectEvent) != undefined && typeof(fnSetObjectEvent) != "undefined"){
        if(typeof(fnSetObjectEvent) == 'function' ) {
            fnSetObjectEvent();
        }
    }

    //FORM 초기값 설정
    if($("#dataForm").length == 1){
        $("#dataForm").setOrgnlDataForm();
    }

    let ua = navigator.userAgent;
    let trident= ua.match(/Trident\/(\d.\d)/i);
    if( navigator.appName.indexOf("Microsoft") > -1 || trident != null){
        lpCom.isIEbrowser = true;
    }

    lpCom.setValidator(); //폼값 체크 설정
});

let lpCom = {};
lpCom.init = function(PARENT_OBJ){
      /**
     * 오브젝트 name 값 자동으로 ID 값을 Name 으로 자동으로 설정
     */
    $("input, select, textarea").each(function() {
        if(lpCom.isEmpty(this.name) && !lpCom.isEmpty(this.id)) this.name = this.id;
    });

    /**
     * ID로  Serialize  생성 return : 문자
     */
    $.fn.serializeById = function() {
      let returning = "";
      $("input, select, textarea", this).each(function() {
          if (this.type != "button" && this.type != "submit" ) // check this to avoid && in returning string
               if(this.type == "checkbox"){
                   if($(this).is(":checked")){
                       returning += '&' + this.id+"="+$(this).data("chkvalue");
                   }else{
                       returning += '&' + this.id+"="+$(this).data("notchkvalue");
                   }
               }else if(this.type == "radio"){
                   returning += '&' + this.id+"="+$(':radio[name='+this.name+']:checked').val();
               }else{
                   returning += '&' + this.id+"="+this.value;
               }
      });
      return returning.substring(1);
    };

    /**
     * NAME 으로  Serialize  생성 return : 문자
     */
    $.fn.serializeByName = function() {
        let returning = "";
        $("input, select, textarea", this).each(function() {
            if (this.type != "button" && this.type != "submit" ) // check this to avoid && in returning string
               if(this.type == "checkbox"){
                   if($(this).is(":checked")){
                       returning += '&' + this.name+"="+$(this).data("chkvalue");
                   }else{
                       returning += '&' + this.name+"="+$(this).data("notchkvalue");
                   }
               }else if(this.type == "radio"){
                   returning += '&' + this.name+"="+$(':radio[name='+this.name+']:checked').val();
               }else{
                   returning += '&' + this.name+"="+this.value;
               }

        });
        return returning.substring(1);
    };

    /**
     * ID로  Serialize  생성 return : JSON 오브젝트
     */
    $.fn.srializeJsonById = function() {
       let returning = {};
       $("input, select, textarea", this).each(function() {
           if (this.type != "button" && this.type != "submit" ){ // check this to avoid && in returning string
               if(this.type == "checkbox"){
                   if($(this).is(":checked")){
                       returning[this.id] = $(this).data("chkvalue");
                   }else{
                       returning[this.id] = $(this).data("notchkvalue");
                   }
               }else if(this.type == "radio"){
                   returning[this.name] = $(':radio[name='+this.name+']:checked').val();
               }else{
                   returning[this.id] = this.value;
               }
           }
       });

       return returning;
     };

     /**
      * ID로  Serialize  생성 return : JSON 오브젝트
      * checkbox
      */
     $.fn.srializeOnlyJsonById = function() {
         let returning = {};
         $("input, select, textarea", this).each(function() {
             if (this.type != "button" && this.type != "submit" ){ // check this to avoid && in returning string
                 if(this.type == "checkbox"){
                     if($(this).is(":checked")){
                         returning[this.id] = $(this).data("chkvalue");
                     }else{
                         returning[this.id] = $(this).data("notchkvalue");
                     }
                 }
             }
         });

         return returning;
     };

     /**
      * NAME 으로 Serialize  생성 return : JSON 오브젝트
      */
     $.fn.srializeJsonByName = function() {
         let returning = {};
         $("input, select, textarea", this).each(function() {
             if (this.type != "button" && this.type != "submit" ) // check this to avoid && in returning string
                if(this.type == "checkbox"){
                   if($(this).is(":checked")){
                       returning[this.name] = $(this).data("chkvalue");
                   }else{
                       returning[this.name] = $(this).data("notchkvalue");
                   }
               }else if(this.type == "radio"){
                   returning[this.name] = $(':radio[name='+this.name+']:checked').val();
               }else{
                   returning[this.name] = this.value;
               }
         });

         return returning;
     };

     $.fn.inputFilter = function(inputFilter) {
         return this.on("input keydown keyup", function(e) {
           if(e.type == "keydown"){
              this.oldValue = this.value;
           }else{
              if (!inputFilter(this.value,this)) {
                 if(this.oldValue != undefined){
                    this.value = this.oldValue;
                 }
              }
           }
         });
     };


     //CheckBox default 값설정
     $.fn.valCheckBox = function(){
          if($(this).is(":checked")){
              return $(this).data("chkvalue");
          }else{
              return $(this).data("notchkvalue");
          }
     };

     //오브젝트 readOnly 설
     $.fn.setReadOnly = function(pReadOnly){
        $(this).each(function(index, item) {
            lpCom.setSelfReadOnly($(item),pReadOnly);
        });

     };

     //FORM 데이터 초기 값 설정
     $.fn.setOrgnlDataForm = function(){
        let orgnlData = $(this).srializeJsonById();
        $(this).data("orgnlData",orgnlData);
     };

     //FORM 데이터 변경 여부
     $.fn.isFormDataChg = function(pIsMsgView){
         let isMsgView = true;
         if(pIsMsgView != undefined) isMsgView = pIsMsgView;
         let orgnlData = $(this).data("orgnlData");
         let chgData = $(this).srializeJsonById();
         if(JSON.stringify(orgnlData) == JSON.stringify(chgData)){
             if(isMsgView){
                 alert("변경된 데이터가 없습니다.");
             }
             return false;
         }else{
             return true;
         }
     };

     //오브젝트 null 확인
     $.fn.isEmpty = function(){
         return lpCom.isEmpty($(this).val());
     };

     /**
     * 필수 입력체크
     */
     $.fn.isRequired = function(){
        if($(this).val() == ""){
           let label = $("label[for="+$(this).attr("id")+"]").html();
           if(label == undefined) label = $(this).attr("data-caption");
           if(label == undefined) label = $(this).attr("placeholder");
            alert(label+" 은(는) 필수 입력 값입니다.");
            $(this).focus();
            return false;
        }else{
            return true;
        }
    };

     //오브젝트 custom value 값 설정
     $.fn.valCustom = function(pVal){
         $(this).val(pVal);

         let type =  $(this).attr("type");
         let thisId = $(this).attr("id");
         let tagName = $(this).prop("tagName");
         if(type == undefined) type = "";
         if(tagName == undefined) tagName = "";

         if(type.toLowerCase() == "checkbox"){
             $(this).prop('checked',($(this).data("chkvalue") == pVal));
         }else if(tagName.toLowerCase() == "select"){
             $(this).attr("data-value",pVal); //삭제여부,사용여부에따른 이전데이터 보기용
         }else if(type.toLowerCase() == "hidden"){
              if($('#'+thisId+'_MULTIPLE').length > 0 ){
                  $(this).val(pVal.split(","));
                  $('#'+thisId+'_MULTIPLE').val(pVal.split(","));
                  $('#'+thisId+'_MULTIPLE').trigger('chosen:updated');
              }
         }

         $(this).change();
     };

     // value 값 비교
     $.fn.equalsVal = function(pVal){
         if($(this).val() == pVal)return true;
         return false;
     };

          {  // date 오브젝트 설정
         $("[data-type=date]",PARENT_OBJ).addClass("cal")
         $("[data-type=date]",PARENT_OBJ).inputFilter(function(value) {
             let notNumber = value.replace(/[0-9]/g, "");
             if(notNumber !== ""){
                return  /^[0-9-]{0,10}$/.test(value);
             }else{
                return  /^[0-9]{0,8}$/.test(value);
             }
         });

         $("[data-type=date]",PARENT_OBJ).datepicker(lpCom.datepickerDefault);
         $("[data-type=month]",PARENT_OBJ).addClass("cal").monthpicker(lpCom.monthpickerDefault);
         $("[data-type=time]",PARENT_OBJ).addClass("clockpicker").attr("data-autoclose","true").clockpicker();
         $("[data-type=time]",PARENT_OBJ).mask("00:00", {placeholder: "__:__"});

         $("[data-type=date",PARENT_OBJ).blur(function(e){
             if(!$(this).is("[readonly]")){
                 let valDate = $(this).val();
                 if(!lpCom.isEmpty(valDate)){
                     valDate = valDate.replace(/[^0-9]/g, ""); //숫자빼고 제거
                     valDate = valDate.replace(/(\d{4})(\d{2})(\d{2})/g, "$1-$2-$3");
                     let pattern = /^(19|20)\d{2}-(0[1-9]|1[012])-(0[1-9]|[12][0-9]|3[0-1])$/;
                     if(!pattern.test(valDate)){
                          alert("올바른 날짜를 입력하세요.");
                          $(this).focus();
                          $(this).val("");
                     }else{
                          $(this).val(valDate);
                     }
                 }
             }
         });

         $("[data-type=date]",PARENT_OBJ).change(function(e){
             //$(this).keyup();
             let val = $(this).val();
             val = val.replace(/(\d{4})(\d{2})(\d{2})/g, "$1-$2-$3");
             $(this).val(val);
             //시작일 최대일 설정
             if(!lpCom.isEmpty($(this).attr("data-date_begin"))){
                let dateBegin =  $(this).attr("data-date_begin");
                if($("#"+dateBegin).val() > val){
                    $("#"+dateBegin).val(val);
                }
             }

             //종료일 최저일 설정
             if(!lpCom.isEmpty($(this).attr("data-date_end"))){
                 let dateEnd =  $(this).attr("data-date_end");
                 if($("#"+dateEnd).val() < val){
                    $("#"+dateEnd).val(val);
                 }
             }
         });

        $("[data-type=month]",PARENT_OBJ).change(function(e){
            //$(this).keyup();
            let val = $(this).val();
            val = val.replace(/(\d{4})(\d{2})/g, "$1-$2");

            $(this).val(val);
            //시작일 최대일 설정
            if(!lpCom.isEmpty($(this).attr("data-month_begin"))){
               let dateBegin =  $(this).attr("data-month_begin");

               if($("#"+dateBegin).val() > val){
                   $("#"+dateBegin).val(val);
               }
            }

            //종료일 최저일 설정
            if(!lpCom.isEmpty($(this).attr("data-month_end"))){
                let dateEnd =  $(this).attr("data-month_end");
                if($("#"+dateEnd).val() < val){
                   $("#"+dateEnd).val(val);
                }
            }
        });


         $("[data-type=month]",PARENT_OBJ).blur(function(e){
             if(!$(this).is("[readonly]")){
                 let valDate = $(this).val();
                 if(!lpCom.isEmpty(valDate)){
                     valDate = valDate.replace(/[^0-9]/g, ""); //숫자빼고 제거
                     if(valDate.length == 6){
                         valDate = valDate.substring(0,4)+"-"+valDate.substring(4,6);
                     }

                     let pattern = /^(19|20)\d{2}-(0[1-9]|1[012])$/;
                     if(!pattern.test(valDate)){
                         alert("올바른 월을 입력하세요.");
                         $(this).focus();
                         $(this).val("");
                     }else{
                         $(this).val(valDate);
                     }
                 }
             }
         });

         $("[data-type=time]",PARENT_OBJ).blur(function(e){
             if(!$(this).is("[readonly]")){
                 let valTime = $(this).val();
                 if(!lpCom.isEmpty(valTime)){
                     let pattern = /^(0[0-9]|1[0-9]|2[0-3]):(0[0-9]|[1-5][0-9])$/;
                     if(!pattern.test(valTime)){
                         alert("올바른 시간을 입력하세요.");
                         $(this).focus();
                         $(this).val("");
                     }else{
                         $(this).val(valTime);
                     }
                 }
             }
         });

         $("[data-type=month]",PARENT_OBJ).keyup(function(e){
             if(!$(this).is("[readonly]")){
                 if(e.keyCode == 13){
                     let valDate = $(this).val();
                     if(valDate.length == 6){
                         valDate = valDate.substring(0,4)+"-"+valDate.substring(4,6);
                         $(this).val(valDate);
                     }
                 }
             }
         });
     }

     {//전화번호
        $("[data-type=telNo]",PARENT_OBJ).inputFilter(function(value, pInputThis) {
             let notNumber = value.replace(/[0-9]/g, "");
             if(notNumber !== ""){
                return  /^[0-9-]{0,13}$/.test(value);
             }else{
                return  /^[0-9]{0,11}$/.test(value);
             }
         });

         $("[data-type=telNo]",PARENT_OBJ).blur(function(e){
             if(!$(this).is("[readonly]")){
                let val = $(this).val();
                val = val.replace(/[^0-9]/g, ""); //숫자빼고 제거
                if(val.startsWith('02')){
                  val = val.replace(/^([0-9]{2})([0-9]{3,4})([0-9]{4})$/g, "$1-$2-$3");
                }else{
                  val = val.replace(/^([0-9]{2,3})([0-9]{3,4})([0-9]{4})$/g, "$1-$2-$3");
                }
                $(this).val(val);
             }
         });

         $("[data-type=telNo]",PARENT_OBJ).focus(function(e){
             if(!$(this).is("[readonly]")){
                 let val = $(this).val();
                 val = val.replace(/[^0-9]/g, ""); //숫자빼고 제거
                 $(this).val(val);
             }
         });

         $("[data-type=telNo]", PARENT_OBJ).each(function(index, item) {
            $(item).blur();
         });
     }

     {//숫자천자리 자동 포멧 소수점 디폴터 3자리
        $("[data-type*=numberFmt]",PARENT_OBJ).inputFilter(function(value, pInputThis) {
           let dataType =  $(pInputThis).attr("data-type");

           let minusReg = "";
           if(dataType.indexOf("-") > -1){
               minusReg  = "-?";
           }

           let numberDecimals = dataType.replace(/numberFmt|\-/g,"");
           let pointReg = ""
           if(numberDecimals != ""){
                pointReg = "[\.]?\\d{0,"+numberDecimals+"}";
           }

           const regex = new RegExp(`^${minusReg}\\d*${pointReg}$`, 'gi');
           return regex.test(value);
        });

        $("[data-type*=numberFmt]",PARENT_OBJ).blur(function(e){
             if(!$(this).is("[readonly]")){
                 let val = $(this).val();
                 val = val.replace(/[^0-9.-]/g, ""); //숫자빼고 제거
                 val = Number(val);
                 $(this).val(lpCom.formatNumber(val));
             }
        });

        $("[data-type*=numberFmt]",PARENT_OBJ).focus(function(e){
             if(!$(this).is("[readonly]")){
                 let val = $(this).val();
                 val = val.replace(/[^0-9.-]/g, ""); //숫자빼고 제거
                 val = Number(val);
                 $(this).val(val);
             }
        });

        $("[data-type*=numberFmt]", PARENT_OBJ).each(function(index, item) {
            $(item).blur();
        });
    }

     //오브젝트 attribute 자동 설정
     $("input, select, checkbox", PARENT_OBJ).each(function() {
         if($(this).prop("tagName") =="SELECT"){

         }else if($(this).prop("type").toLowerCase() =="file"){//파일
            //파일 등록가능한 확장자 처리
            if($(this).attr("extension") != undefined){
                if($(this).attr("extension") == "img"){ //이미지
                    lpCom.setEventImgFileType($(this));
                }else if($(this).attr("extension") == "doc"){ //문서
                    lpCom.setEventDocFileType($(this));
                }else{
                     lpCom.setEventFileType($(this),$(this).attr("extension"));
                }
            }

         }else if(this.type.toLowerCase() =="checkbox"){
             if($(this).data("chkvalue") == undefined){
                $(this).data("chkvalue","Y");
                $(this).data("notchkvalue","N");

                $(this).unbind("change").on('change', function () {
                    if($(this).is(":checked")){
                        $(this).val($(this).data("chkvalue"));
                    }else{
                        $(this).val($(this).data("notchkvalue"));
                    }
                });

                if($(this).val() == $(this).data("chkvalue")){
                     $(this).attr("checked",true);
                }

                $(this).trigger("change");
             }

             if($(this).prop("readonly")){
                 $(this).removeAttr("change");
                 $(this).removeAttr("onclick");
                 $(this).attr("onclick", "return false;");
             }

         }else{
             if($(this).attr("digits") != undefined){  //숫자만 입력하게 설정 정수만
                 $(this).inputFilter(function(value) {
                     return /^\d*$/.test(value);
                 });
             }else if($(this).attr("data-digits_max_length") != undefined){ //숫자 길이제한 처리
                 let digitsMaxLength = $(this).attr("data-digits_max_length");
                 $(this).inputFilter(function(value) {
                     return /^\d*$/.test(value) && value.length <= Number(digitsMaxLength) ;
                 });
             }else if($(this).attr("data-digits_max") != undefined){ //숫자 최대
                 let digitsMax = $(this).attr("data-digits_max");
                 $(this).inputFilter(function(value) {
                     return /^\d*$/.test(value) && value <= Number(digitsMax) ;
                 });
             }else if($(this).attr("number") != undefined){
                 let numberDecimals =  $(this).attr("number");
                 $(this).inputFilter(function(value) {
                    if(numberDecimals == "") numberDecimals = 3;
                    const regex = new RegExp(`^-?\\d*[\.]?\\d{0,${numberDecimals}}$`, 'gi');
                    return regex.test(value);
                 });
             }else if($(this).attr("data-ip") != undefined){
                 $(this).inputFilter(function(value) {
                    return /^[0-9\.]*$/.test(value);
                 });
            }else if($(this).attr("data-number_hyphen") != undefined){
                $(this).inputFilter(function(value) {
                    return /^[0-9\-]*$/.test(value);
                });
             }else if($(this).attr("data-type") == "korEng"){ //한글,영문만
                 $(this).inputFilter(function(value) {
                     return /^[a-zㄱ-ㅣ가-힣]*$/gi.test(value);
                 });
             }else if($(this).attr("data-type") == "digitsEng"){ //숫자,영문만
                 $(this).inputFilter(function(value) {
                     return /^[A-Za-z0-9]*$/g.test(value);
                 });
             }else if($(this).attr("data-max_byte_length") != undefined){
                 let maxByteLength = $(this).attr("data-max_byte_length");
                 $(this).inputFilter(function(value) {
                     if(lpCom.byteCheck(value) <= Number(maxByteLength)){
                         return true;
                     }else{
                         return false;
                     }
                 });
             }else if($(this).attr("data-type") == "digitsOne_1-9"){ //숫자 1-9
                $(this).inputFilter(function(value) {
                    return /^[1-9]?$/.test(value);
                });
             }
         }
     });

    //검색조건 엔터 이벤트 자동설정
    if($("#schFrm").length == 1){
        if(typeof(fnSearch) == 'function' ) {
            $("#schFrm").attr("onsubmit","return false");
            if(!lpCom.contextPath.toLowerCase().includes("frdm")) { //수산자원 제외
                lpCom.enterEventId("schFrm","fnSearch()");
            }
        }
    }


    { //String prototype 추가 설정

        //null,공백확인
        String.prototype.isEmpty = function(){
            return lpCom.isEmpty(this);
        };

        // String 객체에 replaceAll 함수 추가
        String.prototype.replaceAll = function(searchStr, replaceStr) {
            return this.split(searchStr).join(replaceStr);
        };
    }


    //a태그 버튼 클릭스 상단스크롤 움직임 막기
    $('a[href="#"]').unbind("click").click(function(e) {
        e.preventDefault();
        //event.preventDefault() -> 현재 이벤트의 기본 동작을 중단
        //event.stopPropagation() -> 현재 이벤트가 상위로 전파되지 않도록 중단
        //event.stopImmediatePropagation() -> 현재 이벤트가 상위뿐 아니라 현재 레벨에 걸린 다른 이벤트도 동작하지 않도록 중단
    });

    //lpCom.contextPath = "";
}

lpCom.isIEbrowser = false;
lpCom.datepickerDefault = { dateFormat: 'yy-mm-dd',
              numberOfMonths: 1,
              showButtonPanel: true,
              dateFormat: 'yy-mm-dd',
              prevText: '이전 달',
              nextText: '다음 달',
              monthNames: ['1월', '2월', '3월', '4월', '5월', '6월', '7월', '8월', '9월', '10월', '11월', '12월'],
              monthNamesShort: ['1월', '2월', '3월', '4월', '5월', '6월', '7월', '8월', '9월', '10월', '11월', '12월'],
              dayNames: ['일', '월', '화', '수', '목', '금', '토'],
              dayNamesShort: ['일', '월', '화', '수', '목', '금', '토'],
              dayNamesMin: ['일', '월', '화', '수', '목', '금', '토'],
              showMonthAfterYear: true,
              yearRange: '-100:+10',
              yearSuffix: '년',
              closeText: '닫기',
              currentText:'오늘',
              changeMonth: true, //콤보 박스에 월 보이기
              changeYear: true // 콤보 박스에 년도 보이기
};

//달만 선택
//월달력
lpCom.monthpickerDefault = {   pattern: 'yyyy-mm'
                     , monthNames: ['1월','2월','3월','4월','5월','6월','7월','8월','9월','10월','11월','12월']
                     , startYear: 2000
                     , currentText:'오늘'
                     , showButtonPanel: true
                     , closeText: '닫기'
                     , finalYear: (new Date()).getFullYear()+1
}

lpCom.setValidator = function(){

    $.validator.addMethod(
        'alpha', function (value, element) {
            let pattern = /[^a-zA-Z\s]/gi;
            let match = pattern.test(value);
            return !match;
        }, '영문 만 입력가능 합니다.'
    );

   $.validator.addMethod(
        'data-alphaDigits', function (value, element) {
            let pattern = /[^a-zA-Z0-9\s]/gi;
            let match = pattern.test(value);
            return !match;
        }, '영문, 숫자 만 입력가능 합니다.'
    );

   $.validator.addMethod(
       'alphaDigitsHyphen', function (value, element) {
           let pattern = /[^a-zA-Z0-9\-\s]/gi;
           let match = pattern.test(value);
           return !match;
       }, '영문, 숫자, 하이픈 만 입력가능 합니다.'
   );

   $.validator.addMethod(
           'lengthEquals', function (value, element, option) {
               return option == value.length ? true : false;
           }, '문자의 길이는 {0}자만 가능 합니다 '
   );

   $.validator.addMethod(
       'data-password', function (value, element) {
           if(value=="") return true;
           let pattern = /^(?=.*[a-zA-Z])(?=.*[0-9])(?=.*[^&'\\\"<>a-zA-Z0-9])[^&'\\\"<>]{8,20}$/;
           let match = pattern.test(value);
           return match;
       }, "비밀번호는 8~20자 영문,숫자,특수문자 포함를 해야 만 가능합니다.\n사용할수 없는 특수문자 & ' \" < > 입니다."
   );

   $.validator.addMethod(
           'data-ip', function (value, element) {
               if(value=="") return true;
               let pattern = /^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$/;
               let match = pattern.test(value);
               return match;
           }, '올바른 IP가 아닙니다.'
   );

   //부모값 먼저 체크후 필수체크
   $.validator.addMethod(
       'preRequired', function (value, element, option) {
           let id = $(element).attr("id");
           if($("#"+option).val() == "" ||  $("#"+id+" option").size() == 1){
               return true;
           }else{
               return  value != "" ? true : false;
           }
       }, '필수 항목입니다.'
   );

   //checkBox,radio 필수체크
   $.validator.addMethod(
           'data-required_cr', function (value, element,option) {
               let name = $(element).attr("name");
               if($("input:checked[name="+name+"]").length == 0){
                   return false;
               }else{
                   return true;
               }
           }, '필수 항목입니다.'
   );

   //날짜 기간 체크
   $.validator.addMethod(
           'data-dateBegin', function (value, element, option) {
               let id = $(element).attr("id");
               if($("#"+option).val() == "" || $("#"+id).val() == ""){
                   return true;
               }else{
                   return  $("#"+option).val() <= value ? true : false;
               }
           }, '시작 일자보다 이전일자 일수는 없습니다.'
   );


    $.extend( jQuery.validator.messages,{
          required: "필수 항목입니다."
        , remote: "항목을 수정하세요."
        , email: "유효하지 않은 E-Mail주소입니다."
        , url: "유효하지 않은 URL입니다."
        , date: "올바른 날짜를 입력하세요."
        , dateISO: "올바른 날짜(ISO)를 입력하세요."
        , number: "유효한 숫자가 아닙니다."
        , digits: "숫자만 입력 가능합니다."
        , creditcard: "신용카드 번호가 바르지 않습니다."
        , equalTo: "같은 값을 다시 입력하세요."
        , extension: "올바른 확장자가 아닙니다."
        , maxlength: jQuery.validator.format( "{0}자를 넘을 수 없습니다. " )
        , minlength: jQuery.validator.format( "{0}자 이상 입력하세요." )
        , rangelength: jQuery.validator.format( "문자 길이가 {0} 에서 {1} 사이의 값을 입력하세요." )
        , range: jQuery.validator.format( "{0} 에서 {1} 사이의 값을 입력하세요." )
        , max: jQuery.validator.format( "{0} 이하의 값을 입력하세요." )
        , min: jQuery.validator.format( "{0} 이상의 값을 입력하세요." )
       });

    jQuery.validator.setDefaults({
    onkeyup:false,
    onclick:false,
    onfocusout:false,
    focusInvalid:true,
    showErrors:function(errorMap, errorList){
      if(this.numberOfInvalids()) {
        let thisForm = this.currentForm.id;
        let thisId = $(errorList[0].element).attr("id");
        let msg = "";
        let label = $("#"+thisForm+" label[for="+thisId+"]").html();
        let caption = $(errorList[0].element).attr("caption");
        let dataCaption = $(errorList[0].element).attr("data-caption");
        if(caption != undefined){
            msg = caption+" 은(는) " + errorList[0].message;
        }else if(dataCaption != undefined ){
            msg = dataCaption+" 은(는) " + errorList[0].message;
        }else if(label != undefined ){
            msg = label+" 은(는) " + errorList[0].message;
        }else{
            msg = errorList[0].message;
        }
        alert(msg);
        $(errorList[0].element).focus();
      }
    }
    });
};


/**
 * 그룹으로 값 정합성 체크
 */
lpCom.isValidator = function(pTrgt){

     let isValid = true;
     $(pTrgt).each(function(index, item) {
        let label = $("label[for="+$(item).attr("id")+"]").html();
        if(label == undefined) label = $(item).attr("data-caption");
        if(label == undefined) label = $(item).attr("placeholder");

        if($(item).is('[required]')){
            if($(item).val() == "") {
                alert(label+" 은(는) 필수 입력 값입니다.");
                $(item).focus();
                isValid = false;
                return isValid;
            }
        }

        if($(item).is('[data-min_length]')){
            let minLength = $(item).data("min_length");
            minLength = 0|Number(minLength);
            if(minLength == 0) return true;

            if(minLength>$(this).val().length){
                alert(label+" 은(는) {"+ minLength+"} 자 이상 입력하세요.");
                $(item).focus();
                isValid = false;
                return isValid;
             }
        }
     });

     return isValid;
};


/**
 * 내부 오브젝트 정합성 체크
 */
lpCom.isValidatorInsd = function(pTrgt){

    let trgtList = [];
    $("input, select, textarea", pTrgt).each(function(index, item) {
        trgtList.push("#"+item.id);
    });

    return lpCom.isValidator(trgtList.join());
}


/**
 * 트렌젝션 하기전 함수
 */
lpCom.actionBeforeConfirm = function(pMode,pFromObj){
    switch (pMode) {
    case "S":
        msg = "저장 하시겠습니까?";
        break;
    case "I":
        msg = "등록 하시겠습니까?";
        break;
    case "U":
        msg = "수정 하시겠습니까?";
        break;
    case "D":
        msg = "삭제 하시겠습니까?";
        break;
    case "SD":
        msg = "선택한 항목을 삭제 하시겠습니까?";
        break;
    case "DC":
        msg = "삭제취소 하시겠습니까?";
        break;
    default:
        msg = pMode + " 하시겠습니까?";
        break;
    }
    if(pFromObj != undefined ){
        let $requiredCr =  $("INPUT[data-required_cr]");
        $requiredCr.filter(":radio").css("height","1px");
        $requiredCr.filter(":checkbox").css("display","block");
        let isFromValid = pFromObj.valid();
        $requiredCr.filter(":radio").css("height","0px");
        $requiredCr.filter(":checkbox").css("display","none");
        if(!isFromValid) return false;
    }
    return confirm(msg);
};


/**
 * null, 공백 체크
 */
lpCom.isEmpty = function(pStr){
    if( String(pStr) == "" || pStr == undefined || pStr == null || pStr == "undefined"){
        return true;
    }else{
        return false;
    }
};

/**
 * null, 공백 체크 일때 대체 값 리턴
 */
lpCom.isEmptyReplace = function(pStr,pRStr){

    if(lpCom.isEmpty(pStr)){
        return pRStr;
    }else{
        return pStr;
    }
};

/**
 * 사용자 정의 select 설정
 * 예제
 * 1.1개사용 => lpCom.setUserCodeSelect("BOARD_TYPE",{cond:{COND_ID:"S01"},first:"S"});
 * 2.여러개 사용(코드값이 같을때) => lpCom.setUserCodeSelect(["BOARD_TYPE","BOARD_TYPE1"],{cond:{COND_ID:"S01"},first:"S"});
 */
lpCom.setUserCodeSelect = function(pTargetId,pParam){
    pParam.pUrl = "/cmmnCode/selectUserCodeList.do";

   if(pParam.isMultiple){//멀티 셀렉트 일때
        lpCom.setMultiSelectOption(pTargetId,pParam);
    }else{
        return lpCom.setSelectOption(pTargetId,pParam);
    }

}

/**
 * 공통코드 select 설정
 * 1.1개사용 => lpCom.setCodeSelect("BOARD_TYPE",{mastCd:"CD003"],first:"A"});
 * 2.여러개 사용(코드값이 같을때) => lpCom.setCodeSelect(["BOARD_TYPE","BOARD_TYPE1"],{mastCd:"CD003",first:"A"});
 * 3.여러개 사용(코드값이 다를때) => lpCom.setCodeSelect(["BOARD_TYPE","BOARD_TYPE1"],{mastCd:["CD003","CD004"],first:"A"});
 */
lpCom.setCodeSelect = function(pTargetId,pParam){
    pParam.pUrl = "/cmmnCode/selectCodeList.do";
    if(!pParam.hasOwnProperty("cond")) pParam.cond = {};
    pParam.cond.mastCd = pParam.mastCd;

    if(pParam.isMultiple){//멀티 셀렉트 일때
        lpCom.setMultiSelectOption(pTargetId,pParam);
    }else{
        return lpCom.setSelectOption(pTargetId,pParam);
    }
}

/**
 * 콤보박스 아이템 설정
 *
 */
lpCom.setSelectOption = function(pTargetId,pParam){

    if(!pParam.hasOwnProperty("first")) pParam.first = "A"; // A:전체,S:선택, A S 가 아니면 그대로 출력
    if(!pParam.hasOwnProperty("cond")) pParam.cond = {};
    if(!pParam.hasOwnProperty("notValue")) pParam.notValue = [];
    if(!pParam.hasOwnProperty("multiple")) pParam.multiple = false;
    if(!pParam.hasOwnProperty("isChange")) pParam.isChange = false;
    if(!pParam.hasOwnProperty("dtlCdEtc")) pParam.dtlCdEtc = []; //상세코드 기타(01,02,03)

    let comboData = [];
    let targetArr = [];


    if(!$.isArray(pTargetId)){
        targetArr.push(pTargetId);
    }else{
        targetArr = pTargetId;
    }


    //공통코드일때만
    let condCodeUpperArr = [];
    if(pParam.cond.hasOwnProperty("mastCd")){
        if(!$.isArray(pParam.cond.mastCd)){
            //대상오브젝트 갯수별 설정
            for(let i=0; i<targetArr.length; i++){
                condCodeUpperArr.push(pParam.cond.mastCd);
            }
        }else{
            condCodeUpperArr = pParam.cond.mastCd;
        }
        if(targetArr.length != condCodeUpperArr.length){
            alert("공통코드 대상오브젝트 배열 갯수와 조건 코드 배열 갯수가 같아야 합니다.");
            return;
        }

        pParam.cond.mastCdList = JSON.stringify(condCodeUpperArr);
    }

    let chkNotValue = {};
    for(let i=0; i<pParam.notValue.length; i++){
        chkNotValue[pParam.notValue[i]] = true;
    }
    $.ajax({
        url : lpCom.contextPath+pParam.pUrl,
        data : pParam.cond,
        async : false,
        type : "POST",
        success : function(data){
            comboData = data.list;
        },
        error:function(request,status,error){
            alert("조회오류");
        }
    });

    switch(pParam.first){
        case "S":
            comboData.unshift({cd:"",cdNm:"선택"});
            break;
        case "A":
            comboData.unshift({cd:"",cdNm:"전체"});
             break;
        case "X":
            break;
        default:
            comboData.unshift({cd:"",cdNm:pParam.first});
            break;
    }

     if(pTargetId != "" ){

         for(let j=0; j<targetArr.length; j++){
             let targetId = targetArr[j];

             let selectCd = "";
             if(!lpCom.isEmpty($("#"+targetId).attr("data-value"))){
                 selectCd = $("#"+targetId).attr("data-value"); // 초기값 셋팅시 오브젝트에 value 값이 우선적용됨
                 $("#"+targetId).removeAttr("data-value");
             }

             $("#"+targetId+" > option").remove();

             for(let i=0; i<comboData.length; i++){
                 //공통코드일때만
                 if(pParam.cond.hasOwnProperty("mastCd")){
                     if(comboData[i].cd !="" && comboData[i].mastCd != condCodeUpperArr[j]) continue;
                 }
                 //제거코드값
                 if(chkNotValue.hasOwnProperty(comboData[i].cd)) continue;
                  //사용여부에 따른 이전자료 보기 위함
                 if(selectCd != comboData[i].cd
                         && ((comboData[i].hasOwnProperty("useYn") && comboData[i].useYn != "Y") || (comboData[i].hasOwnProperty("delYn") && comboData[i].delYn != "N")   )){
                     continue;
                 }

                 if ($("#" + targetId).attr('data-option-num') == undefined || comboData[i].cd == "") {
                     $("#" + targetId).append("<option value='" + comboData[i].cd + "'>" + comboData[i].cdNm + "</option>");
                 } else {
                     $("#" + targetId).append("<option value='" + comboData[i].cd + "'>" + comboData[i].cd + "." + comboData[i].cdNm + "</option>");
                 }

                 //상세코드 기타
                 if (pParam.dtlCdEtc.length > 0) {
                     for (let j = 0; j < pParam.dtlCdEtc.length; j++) {
                         let dtlCdEtcNo = pParam.dtlCdEtc[j];
                         $("#" + targetId + " option:eq(" + i + ")").attr("data-dtl_cd_etc_" + dtlCdEtcNo, comboData[i]["dtlCdEtc" + dtlCdEtcNo]);
                     }
                 }

             }


             if(selectCd != ""){
                  $("#"+targetId).val(selectCd);
                  if(lpCom.isEmpty($("#"+targetId).val())){ //콤박스에 해당 값이 없으면 첫번째 option selected
                      $("#"+targetId+" option:eq(0)").attr('selected', 'selected'); // 첫번째 option selected
                  }
             }else{
                 $("#"+targetId+" option:eq(0)").attr('selected', 'selected'); // 첫번째 option selected
             }

             if(pParam.isChange){
                 $("#"+targetId).trigger("change");
             }

             /*
             if($("#"+targetId).hasClass("chosen-select")){
                 $("#"+targetId).chosen({no_results_text: "nothing found"});
             }
             */
         }
    }else{
         //제거 코드값
         comboData = comboData.filter(function(value) {
            return !chkNotValue.hasOwnProperty(value.cd)
         });

    }
    return comboData;
};

lpCom.setMultiSelectOption = function(pTargetId,pParam){
    if(!pParam.hasOwnProperty("cond")) pParam.cond = {};
    if(!pParam.hasOwnProperty("notValue")) pParam.notValue = [];

    let comboData = [];
    let targetArr = [];


    if(!$.isArray(pTargetId)){
        targetArr.push(pTargetId);
    }else{
        targetArr = pTargetId;
    }


     let condCodeUpperArr = [];
    //공통코드일때만
    if(pParam.cond.hasOwnProperty("mastCd")){
        if(!$.isArray(pParam.cond.mastCd)){
            //대상오브젝트 갯수별 설정
            for(let i=0; i<targetArr.length; i++){
                condCodeUpperArr.push(pParam.cond.mastCd);
            }
        }else{
            condCodeUpperArr = pParam.cond.mastCd;
        }
        if(targetArr.length != condCodeUpperArr.length){
            alert("공통코드 대상오브젝트 배열 갯수와 조건 코드 배열 갯수가 같아야 합니다.");
            return;
        }

        pParam.cond.mastCdList = JSON.stringify(condCodeUpperArr);
    }

    let chkNotValue = {};
    for(let i=0; i<pParam.notValue.length; i++){
        chkNotValue[pParam.notValue[i]] = true;
    }

    $.ajax({
        url : lpCom.contextPath+pParam.pUrl,
        data : pParam.cond,
        async : false,
        type : "POST",
        success : function(data){
            comboData = data.list;
        },
        error:function(request,status,error){
            alert(error);
        }
    });


        switch(pParam.first){
        case "A":
            comboData.unshift({cd:"",cdNm:"전체"});
            break;
    }

     if(pTargetId != "" ){

         for(let j=0; j<targetArr.length; j++){
             let targetId = targetArr[j];
             let newTargetId = targetId+"_MULTIPLE";
             if($("#"+newTargetId).length == 0){
                 $("#"+targetId).attr("name",newTargetId);
                 $("#"+targetId).attr("multiple",true);
                 $("#"+targetId).addClass("chosen-select");
                 $("#"+targetId).attr("id",newTargetId);
                 $("#"+newTargetId).after("<input type='hidden' name='"+targetId+"' id='"+targetId+"'>");
                 $("#"+newTargetId).chosen();

                if(pParam.first == "A"){
                    //전체 옵션 있을때만
                    $(document).on("click", "#"+newTargetId+"_chosen .chosen-results li", function() {
                        if($(this).index() ==0 && $("#"+newTargetId).data("optionAll") != ""){
                            let optionAll = $("#"+newTargetId).data("optionAll").split(",");
                            $("#"+newTargetId).val(optionAll)
                            $("#"+targetId).val(optionAll);
                            $("#"+newTargetId).trigger('chosen:updated');
                         }
                    });
                }

                 $("#"+newTargetId).on('change', function () {
                    $("#"+targetId).val($(this).val());
                 });
             }

             let selectCd = "";

             if(!lpCom.isEmpty($("#"+targetId).attr("value"))){
                 selectCd = $("#"+targetId).attr("value");
             }

             $("#"+newTargetId+" > option").remove();

             let optionAll = [];
             for(let i=0; i<comboData.length; i++){
                 //공통코드일때만
                 if(pParam.cond.hasOwnProperty("mastCd")){
                     if(comboData[i].cd !="" && comboData[i].mastCd != condCodeUpperArr[j]) continue;
                 }
                 if(chkNotValue.hasOwnProperty(comboData[i].cd)) continue; //제거코드값

                 //사용여부에 따른 이전자료 보기 위함
                 if((selectCd == "" || comboData[i].cd.indexOf(selectCd) == -1) && comboData[i].hasOwnProperty("useYn") && comboData[i].useYn != "Y" ){
                     continue;
                 }
                 if(comboData[i].cd != ""){
                     optionAll.push(comboData[i].cd);
                 }
                 $("#"+newTargetId).append("<option value='"+comboData[i].cd+"'>"+comboData[i].cdNm+"</option>");
             }

             $("#"+newTargetId).data("optionAll",optionAll.join(","));

             if(!lpCom.isEmpty($("#"+newTargetId).attr("data-value"))){
                 $("#"+newTargetId).val($("#"+newTargetId).attr("data-value").split(","))
                 $("#"+targetId).val($("#"+newTargetId).attr("data-value").split(","))
                 $("#"+newTargetId).attr("data-value","");
             }

             $("#"+newTargetId).trigger('chosen:updated');
         }
    }
}

/**
 * Ajax 통신
 */

lpCom.Ajax = function(pSid, pUrl, pParam, pCallBackFunc, pOtherInit){

    let defaultOtherInit ={isSuccesMsg:true,isShowLoding:true,isErrorMsg:true,isErrCallBackFunc:false,isAsync:true,resultMsg:"처리 완료 하였습니다."};
    //조회면 결과 메세지 처리 안함
    if(pSid.indexOf("search") > -1 || pSid.indexOf("Search") > -1){
        defaultOtherInit.isSuccesMsg = false;
    }

    let otherInit = $.extend(true, defaultOtherInit, pOtherInit);

    //AUIGRID 사용시
    if(otherInit.hasOwnProperty("auiGridObj")){
       //그리드 로딩 이미지 표현
       otherInit.isShowLoding = false;
       AUIGrid.showAjaxLoader(otherInit.auiGridObj.myGridID);
       //사용자 페이징 처리시
       if(otherInit.auiGridObj.auiGridProps.useCustomPaging) {
           pParam.selectPage = otherInit.auiGridObj.selectPage; // 선택 페이지
           pParam.rowCountPage = otherInit.auiGridObj.rowCountPage ; //한화면 ROW 건수
       }
    }

    if(pUrl.substring(0,1) != "."){
        pUrl = lpCom.contextPath+pUrl;
    }

    let ajaxSetup = {
            url: pUrl
            , data : pParam
            , contentType : "application/x-www-form-urlencoded"
            , async : otherInit.isAsync
            , type: "POST"
            , dataType: "json"
            , success: function(data) {
                 data.result = "Success";
                 data.resultMsg = otherInit.resultMsg;
                 if(otherInit.isSuccesMsg) alert(otherInit.resultMsg);
                 if(pCallBackFunc != undefined){
                     if(typeof(pCallBackFunc) == 'function' ) {
                         pCallBackFunc(pSid,data);
                     }else{
                         alert("콜백 함수가 없습니다.");
                     }
                 }
            }
            , beforeSend  : function(jqXHR,settings) {
                if (otherInit.isShowLoding) {
                this.lodingDiv = lpCom.loadingDivCreate();
                // document.body.appendChild(this.lodingDiv);
                window.top.document.body.appendChild(this.lodingDiv); //전체 화면 표시 할때

                }
            }
            , complete : function() {
                if (otherInit.isShowLoding) {
                    window.top.document.body.removeChild(this.lodingDiv); //전체 화면 표시 할때
                }
            }
            , error: function(data) {
                 if(data.status == 400){
                     if(data.responseJSON.resultMsg !="") {
                        if(otherInit.isErrorMsg) {
                            alert(data.responseJSON.resultMsg);
                        }
                     }
                     if(otherInit.isErrCallBackFunc){
                         if(pCallBackFunc != undefined){
                             if(typeof(pCallBackFunc) == 'function' ) {
                                 pCallBackFunc(pSid,data.responseJSON);
                             }else{
                                 alert("콜백 함수가 없습니다.");
                             }
                         }
                     }
                 }else if(data.status == 401){
                     //로그인,권한체크만 사용
                     alert(data.responseJSON.resultMsg);
                     top.location.href = lpCom.contextPath+"/login.do"; //로그인 페이지로 이동
                 }else{
                     //페이지 에러 페이지로 이동할지
                     alert("관리자에게 문의 바랍니다.");
                 }
             }
        };

    if(otherInit.hasOwnProperty("formObj")){
        if(otherInit.formObj.length == 0 ){
            alert("해당 form 이 정의 되지 않았습니다.");
            return;
        }
        otherInit.formObj.ajaxSubmit(ajaxSetup);    //form 전송(파일)
    }else{

        $.ajax(ajaxSetup);
    }
};

/**
 * Ajax 통신 콜백 없이 리턴
 */
lpCom.AjaxNotCallBack = function(pUrl, pParam){
    let retData = {};

    if(pUrl.substring(0,1) != "."){
        pUrl = lpCom.contextPath+pUrl;
    }

    $.ajax({
        url : pUrl,
        data : pParam,
        async : false,
        type : "POST",
        success : function(data){
            retData = data
        },
        error:function(request,status,error){
            alert(error);
        }
    });
    return retData;
}

/**
 * 공통 팝업
 * */
lpCom.winOpen = function (url, title, params, opt) {

        if(url.substring(0,1) == "/"){ //절대 경로 일때는
            url = lpCom.contextPath+url;
        }

        // opt : left , top , width , height , toolbar , menubar , scrollbars , status , resizable
        // toolbar , menubar , scrollbars , status , resizable은 Default값을 가짐
        if(opt == undefined) opt = {};
        if(params == undefined) params = {};

        let optStr = "";
        opt.width = opt.width||"600" ;
        opt.height = opt.height||"400" ;

        if (opt.width != null && opt.height != null) {
            let left = screen.width / 2 - (Number(opt.width) / 2);
            let top = screen.height / 2 - (Number(opt.height) / 2);
            optStr += "left=" + left + ",top=" + top;
        }
        for (let o in opt) {
            optStr += "," + o.toString() + "=" + opt[o].toString();
        }

        let paramStr = "";
        for (let p in params) {
            paramStr +=  "&" + p.toString() + "=" + params[p].toString();
        }
        if(url.indexOf("?") == -1 && paramStr != ""){
            paramStr = "?"+ paramStr.substring(1);
        }
        if (optStr.toLowerCase().indexOf("toolbar") == "-1") { optStr += ",toolbar=no"; }
        if (optStr.toLowerCase().indexOf("menubar") == "-1") { optStr += ",menubar=no"; }
        if (optStr.toLowerCase().indexOf("status") == "-1") { optStr += ",status=no"; }
        if (optStr.toLowerCase().indexOf("scrollbars") == "-1") { optStr += ",scrollbars=no"; }
        if (optStr.toLowerCase().indexOf("resizable") == "-1") { optStr += ",resizable=no"; }

        window.open(url + encodeURI(paramStr), title, optStr);
    };

/**
 * 현재 날짜
 */
lpCom.getCurrentDate= function(pDelimiter){

    let newDate = new Date();
    let year = newDate.getFullYear();
    let month = newDate.getMonth() + 1;
    let date = newDate.getDate();

    let retval;
    if (month < 10) month = "0" + month;
    if (date < 10)date = "0" + date;
    let delimiter = "-";
    if (pDelimiter != undefined) delimiter = pDelimiter;
    return year +delimiter+ month +delimiter+ date;
};

/**
 * 이전, 이후 날짜 JSON 데이터 리턴
 */
lpCom.getJsonPreNextDay = function (pDate,pDayCnt,pDelimiter) {

    if(pDate.length == 8) {
         pDate =  pDate.substr(0,4)+"-"+pDate.substr(4,2)+"-"+pDate.substr(6,2)
    }

    let newDate = new Date(pDate);
    if(pDate == "") newDate = new Date();
    newDate.setDate(newDate.getDate() + pDayCnt);

    let year = newDate.getFullYear();
    let month = newDate.getMonth()+1;
    let day = newDate.getDate();

    let retval;
    if (month < 10) month = "0" + month;
    if (day < 10) day = "0" + day;
    let delimiter = "-";
    if (pDelimiter != undefined) delimiter = pDelimiter;
    let date  =year+delimiter+month+delimiter+day;

    return {year:year,month:month,day:day,date:date};
};

/**
 * FORM action submit
 */
lpCom.submit = function(pUrl, pFormNm){
    let form = document.getElementsByTagName("form");

    let targetForm = null;

    let formNm = "frm";
    if(pFormNm != undefined) formNm = pFormNm
    for(let i=0; i<form.length; i++){
        if(form[i].name == formNm) {
           targetForm = form[i];
           form[i].method = "post";
           break;
        }
    }

    if(targetForm  == null){
        alert("해당 폼 정보가 없습니다.(default:frm)");
        return;
    }

    if(pUrl.substring(0,1) == "/"){ //절대 경로 일때는
        pUrl = lpCom.contextPath+pUrl;
    }

    targetForm.action = pUrl;
    targetForm.submit();
};

/**
 * location.href
 */
lpCom.href = function(pUrl){
    if(pUrl.substring(0,1) == "/"){ //절대 경로 일때는
        pUrl = lpCom.contextPath+pUrl;
    }

    location.href = pUrl;
};

/**
 * 현재 페이지 다시 location.href
 */
lpCom.hrefCurrent = function(param){

    location.href = location.pathname+"?"+lpCom.serializeByJsonData(param);
};

/**
 * enter 처리
 * */
lpCom.enterEventId = function(id_name, fn_name) {
    $("#" + id_name).unbind("keyup").keyup(function(event) {
        if (event.keyCode == 13) {
            new Function('return '+fn_name)();
        }
    });
};

/**
 * 고정 콤보 박스 설정
 *
 * */
lpCom.setFixCombo = function(pTargetId,pDataGbn,pFirst){
    let comboData = [];
    let newDate = new Date();
    let year = newDate.getFullYear();

    switch(pDataGbn){
        case "C01" : // 년도
            for(let i=year+1; i>=2000; i--){
                comboData.push({cd:i,cdNm:i+"년"});
            }
            break;
        case "C02" : // 월
            for(let i=1; i<=12; i++){
                let mon = lpCom.lpad(i+"",2,"0");
                comboData.push({cd:mon,cdNm:mon+"월"});
            }
            break;
        case "C03" : // 현재 년도까지
            for(let i=year; i>=2000; i--){
                comboData.push({cd:i,cdNm:i+"년"});
            }
            break;
        case "C04" : // Email
            comboData.push({cd:"", cdNm:"직접입력"});
            comboData.push({cd:"hotmail.com", cdNm:"hotmail.com"});
            comboData.push({cd:"gmail.com", cdNm:"gmail.com"});
            comboData.push({cd:"naver.com", cdNm:"naver.com"});
            comboData.push({cd:"nate.com", cdNm:"nate.com"});
            comboData.push({cd:"korea.kr", cdNm:"korea.kr"});
            break;
        case "C05" : //1 ~ 10
            for ( let i = 1; i <= 10; i++ ) {
                  comboData.push({cd:i,cdNm:i+"회"});
            }
            break;
        case "C06" : //1 ~ 5 년
            for ( let i = 1; i <= 5; i++ ) {
                 comboData.push({cd:i,cdNm:i+"년"});
            }
            break;
       case "C07" : // 일
            for(let i=9; i<=20; i++){
                comboData.push({cd:i*10,cdNm:(i*10)+"일"});
            }
            break;
       case "C08" : // 0 ~ 5
           for ( let i = 0; i <= 5; i++ ) {
                  comboData.push({cd:i,cdNm:i+"개"});
            }
            break;
       case "C09" : // 0 ~ 5
           for ( let i = 1; i <= 10; i++ ) {
                  comboData.push({cd:i,cdNm:i+"일"});
            }
           break;
       case "C10" : // 5,10,20,30
            comboData.push({cd:"5", cdNm:"5"});
            comboData.push({cd:"10", cdNm:"10"});
            comboData.push({cd:"20", cdNm:"20"});
            comboData.push({cd:"30", cdNm:"30"});
            break;
      case "C11" : // 1 ~ 15 첨부파일
           comboData.push({cd:"0", cdNm:"제한없음"});
           for ( let i = 1; i <= 15; i++ ) {
                  comboData.push({cd:i,cdNm:i+"개"});
            }
           break;

    }

    switch(pFirst){
        case "S":
            comboData.unshift({cd:"",cdNm:"선택"});
            break;
        case "A":
            comboData.unshift({cd:"",cdNm:"전체"});
         break;
        case "X":
            break;
        default:
            comboData.unshift({cd:"",cdNm:pFirst});
            break;
    }


    if(pTargetId != "" ){
        $("#"+pTargetId+" > option").remove();
            comboData.forEach(function (rowData) {
            $("#"+pTargetId).append("<option value='"+rowData.cd+"'>"+rowData.cdNm+"</option>");
        });

        if(!lpCom.isEmpty($("#"+pTargetId).attr("data-value"))){
            $("#"+pTargetId).val($("#"+pTargetId).attr("data-value")); // 초기값 셋팅시 오브젝트에 value 값이 우선적용됨
            $("#"+pTargetId).removeAttr("data-value");
        }


    }else{
        //아이디 없을때 콤보 데이터 리턴
        return comboData;
    }

};

/**
 * 로딩 DIV 생성
 */
lpCom.loadingDivCreate = function(){

    //로딩중 DIV 이미지 생성
    let now = new Date(); //현재 날짜 가져오기
    let lodingBgDiv = document.createElement("div");
    let lodingDiv = document.createElement("div");
    let subDiv = document.createElement("div");
    subDiv.setAttribute("id","loading");
    let subSpan = document.createElement("span");
    subSpan.append("Loading...");

    lodingBgDiv.setAttribute("style"," width:100%; height:100%;" +
                      " background-color: rgba(0,0,0,.0);" +
                      " position:fixed; z-index:9999;"+
                      " id:loading_div"+now.getMilliseconds() +";"+
                      " top:0px;" ) ;

    lodingDiv.setAttribute("class","loading-wrap");

    lodingDiv.append(subDiv);
    lodingDiv.append(subSpan);
    lodingBgDiv.append(lodingDiv);
    return lodingBgDiv;
};


/**
 * TEXTAREA.INPUT,SELECT 오브젝트 readOnly 동적 설정 함수
 * 예)lpCom.setObjReadOnly(true); //targetObj 없으면 전체 있으면 하위 모든 오브젝트 기준으로 실행됨
 * 오브젝트 readOnly 동적 변경이 필요 없을시 오브젝트에 data-readonly_exclude 추가 <input type="text" data-readonly_exclude="true">
 */
lpCom.setObjReadOnly = function(pReadOnly, pTargetObj,pOtherObjArr){
     let targetObj = pTargetObj||"";
     $(":input",targetObj).each(function(){ //TEXTAREA.INPUT,SELECT
        if($(this).attr("data-readonly_exclude") == undefined || $(this).attr("data-readonly_exclude") == "false"){
            lpCom.setSelfReadOnly($(this),pReadOnly);
        }
     });

     //data-readonly_exclude 상관없이 무조건 실행
     if(pOtherObjArr != undefined){
         for(let i=0; i<pOtherObjArr.length; i++){
            if($(pOtherObjArr[i]).length > 0){
                lpCom.setSelfReadOnly($(pOtherObjArr[i]),pReadOnly);
            }
         }
     }

};

/**
 * TEXTAREA.INPUT,SELECT 오브젝트 readOnly 동적 설정 함수
 * 예)lpCom.setSelfReadOnly(pTagetObj,true);
 *
 */
lpCom.setSelfReadOnly = function(pTagetObj,pReadOnly){
    let objTagName = pTagetObj.get(0).tagName;
    objTagName = objTagName.toLowerCase();

    let objType = pTagetObj.attr("type");
    let objDataType = pTagetObj.attr("data-type");
    if(objType == undefined) objType = "text";
    objType = objType.toLowerCase();

    let objId = pTagetObj.attr("id");
    if(objTagName == "button" ||  objId == undefined || (objType == "hidden"  && objId.indexOf("_MULTIPLE") == -1)){
        return;
    }

    pTagetObj.attr("readonly",pReadOnly);
   /* if(pReadOnly){
         pTagetObj.css("background-color","");
    }else{
         pTagetObj.css("background-color","#fff");
    }*/


     switch(objTagName){
         case "input" :
              if(objType == "text" || objType == "textbox" ){
                  if(pReadOnly){
                     if(objDataType=="date"){
                         pTagetObj.datepicker('destroy');
                         pTagetObj.css("background-image","none");
                     }
                  }else{
                      if(objDataType=="date"){
                       pTagetObj.datepicker('destroy');
                       pTagetObj.datepicker(lpCom.datepickerDefault);
                       pTagetObj.css("background-image","");
                     }
                  }
              } else if(objType == "hidden" ){
                   if($('#'+pTagetObj.attr("id")+'_MULTIPLE').length > 0 ){
                       if(pReadOnly){
                           $('#'+pTagetObj.attr("id")+'_MULTIPLE').prop('disabled', true).trigger("chosen:updated");
                       }else{
                           $('#'+pTagetObj.attr("id")+'_MULTIPLE').prop('disabled', false).trigger("chosen:updated");
                       }
                   }
              }else if(objType == "radio"){
                 if(pReadOnly){
                     $("[name="+pTagetObj.attr("name")+"]:not(:checked)").attr('disabled', 'disabled');
                 }else{
                     $("[name="+pTagetObj.attr("name")+"]").removeAttr('disabled');
                 }
              }else if(objType == "checkbox"  ){
                  if(pReadOnly){
                      $("[name="+pTagetObj.attr("name")+"]").attr('disabled', 'disabled');
                  }else{
                      $("[name="+pTagetObj.attr("name")+"]").removeAttr('disabled');
                  }
              }
              break;
     case "textarea" :

         break;
     case "select" :
          if(pReadOnly){
              pTagetObj.find("option").not(":selected").attr("disabled", "disabled");
          }else{
              pTagetObj.find("option").removeAttr("disabled");
          }

         /*
            //pTagetObj.children("option").not(":selected").attr("style", pReadOnly ? 'display:none': 'display:' );
           pTagetObj.children("option").not(":selected").remove();
            if(pReadOnly){
                pTagetObj.addClass("input-std-readonly");
            }else{
                pTagetObj.removeClass("input-std-readonly");
            }

             let _lable_Obj = "_label_"+pTagetObj.attr("id");
             $('#'+_lable_Obj).remove();
             if(pReadOnly){

                 let tmpObj =  $("<input type='text' id='"+_lable_Obj+"'>");
                 tmpObj.attr("value",(lpCom.isEmpty(pTagetObj.find(' option:selected').val()) ? "" :pTagetObj.find(' option:selected').text()));
                 tmpObj.attr("readonly",pReadOnly);
                 tmpObj.css("width",pTagetObj.css("width"));
                 tmpObj.css("height",pTagetObj.css("height"));
                 tmpObj.addClass("input-std-readonly");
                 pTagetObj.after(tmpObj);
                 pTagetObj.css("display","none");
             }else{
                 pTagetObj.css("display","");
             }
             */
         break;
   }
};

//lpad
lpCom.lpad = function(s, padLength, padString){

    while(s.length < padLength)
        s = padString + s;
    return s;
};

//rpad
lpCom.rpad = function(s, padLength, padString){
    while(s.length < padLength)
        s += padString;
    return s;
};

//현제일자
lpCom.getToday = function(format){

    let date=new Date();
    let dt=date.getFullYear() +format+ lpCom.lpad((date.getMonth()+1)+"",2,"0") +format+ lpCom.lpad(date.getDate()+"",2,"0");
    return dt;
};


/**
 * 현재 시간
 */
lpCom.getCurrentTime = function(pDelimiter){

    let now = new Date();
    let hours = now.getHours();
    let minutes = now.getMinutes();
    let seconds = now.getSeconds();

    // 10보다 작을 경우 앞에 '0'을 추가하여 2자리 수로 만들기
    hours = hours < 10 ? '0' + hours : hours;
    minutes = minutes < 10 ? '0' + minutes : minutes;
    seconds = seconds < 10 ? '0' + seconds : seconds;

    let delimiter = ":";
    if (pDelimiter != undefined) delimiter = pDelimiter;

    return timeString = hours + delimiter + minutes + delimiter;
};


//첨부파일 다운로드
lpCom.fnFileDown = function(fileName,orgFileName){

    let params = "fileName="+encodeURIComponent(fileName);  //저장된 파일명
    if(!lpCom.isEmpty(orgFileName)) {
        params += "&orgFileName="+encodeURIComponent(orgFileName);    //실제 파일명
    }

    location.href = lpCom.contextPath+"/BT/com/fileDown.jsp?"+params;
};

/**
 * 데이터 값으로 폼값 자동 설정
 * */
lpCom.setFormValByData = function(pData){
   for(let objId in pData){
        let obj = $("#"+objId);
        if(obj.attr("type") == "file") continue;
        obj.val(pData[objId]);
    }
};



/**
 * 해당 오브젝트 문서 파일 체크 타입 change 이벤트 설정
 */
lpCom.setEventDocFileType = function(pObj){
    lpCom.setEventFileType(pObj,"hwp|xls|pdf|xlsx|txt");
};

/**
 * 해당 오브젝트 이미지 파일 체크 타입 change 이벤트 설정
 */
lpCom.setEventImgFileType = function(pObj){
    lpCom.setEventFileType(pObj,"bmp|gif|jpg|jpeg|png");
};

/**
 * 해당 오브젝트 사용자 설정 파일 체크 change 이벤트 설정
 */
lpCom.setEventFileType = function(pObj,pComfirmNm){
      pObj.unbind("bind").bind("change",function(event,param){
            let fileFormat = "\.("+pComfirmNm+")$";
            if((new RegExp(fileFormat, "i")).test($(this).val()))return true;

            alert($(this).val()+"는 등록 할수 없는 파일 입니다.");
            if(lpCom.isIEbrowser){
                $(this).replaceWith($(this).clone(true) );
            }else {
                $(this).val("");
            }
        });
};

/**
 * 해당페이지 오보젝트 값으로 파라메터 설정
 */
lpCom.setPageParamByObj = function(pParamJson,pKey){
    if(pKey == undefined){
        let href = location.href;
        let hrefArr = href.split("/");
        let pKey = hrefArr[hrefArr.length-1].split(".")[0];
    }
    sessionStorage.setItem(pKey, JSON.stringify(pParamJson));
};

/**
 * 해당 페이지 파라메서 값으로 오브젝트 값 설정
 */
lpCom.setPageObjByParam = function(pKey){
    if(pKey == undefined){
        let href = location.href;
        let hrefArr = href.split("/");
        let pKey = hrefArr[hrefArr.length-1].split(".")[0];
    }

    let paramDataStr = sessionStorage.getItem(pKey);
    if(paramDataStr != undefined){
        let paramData = JSON.parse(paramDataStr);
        for(let objId in paramData ){
           if($("#"+objId).attr("type") == "checkbox" ){
               if(paramData[objId] == $("#"+objId).data("chkvalue")){
                   $("#"+objId).attr("checked",true);
               }
           }else if($("#"+objId).attr("type") == "radio"){
               $("[name="+objId+"]:input:radio[value='"+paramData[objId]+"']").attr("checked",true);
           }else{
               $("#"+objId).val(paramData[objId]);
           }
        }
        sessionStorage.removeItem(pKey);
        return paramData;
    }

    return {};
};

//다이얼로그 오픈
lpCom.dialogOpen = function (opt) {

    if(opt == undefined) opt = {};

    if(lpCom.isEmpty(opt.dialogNm)) opt.dialogNm = "dialog";

    let dialog = $("#"+opt.dialogNm);

    $(dialog).html(opt.contents);

    let top = screen.height / 2 - (Number(200) / 2);

    opt.width = opt.width||"250" ;
    opt.height = opt.height||"200" ;

    $(dialog).dialog({
        modal: true,
        resizable: false,
        height:opt.height,
        width:opt.width,
        position: {
                my: "center",
                at: "top+"+top,
                of: window
        },
        title: opt.title,
        buttons: opt.buttons
    });
    if(lpCom.isEmpty(opt.title)) {
        $(dialog).siblings('div.ui-dialog-titlebar').remove();
    }

};

// 스페이스, 엔터키 제거
lpCom.fn_removeSpaceEnter = function(str) {

    str = str.trim();
    str = str.replace(/\n/g, "");
    return str;
};


/**
 * input box 입력제어
 * 예)lpCom.valdInputCheck("frm");
 */
lpCom.valdInputCheck = function(obj) {

    if(obj == undefined) return;

    $(obj+" input, textarea").bind("keyup",function(event){
        //숫자
        if($(this).attr("digits")) {
            this.value = this.value.replace(/[^0-9]/g,'');
        }
        //영문
        if($(this).attr("alpha")) {
            this.value = this.value.replace(/[^a-zA-Z\s]/g,'');
        }
    });
};

/**
 * 팝업여부
 * true : 팝업
 * */
lpCom.isPopup = function(){
    if (opener && !opener.closed) {
        return true;
    } else {
        return false;
    }
};


/**
 * 천자리 콤마 포멧
 */

lpCom.formatNumber = function(str){
  return str.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");

};

/**
 * 검색조건 입력유무
 * return 값 있으면.. false
 */

lpCom.searchInputCheck = function(obj) {

    if(obj == undefined) return;

    let ret = true;
    $("#"+obj).each(function() {
        $("input ,select", this).each(function() {
            if(this.type == "select-one" || this.type == "text") {
                if(!lpCom.isEmpty(this.value)) {
                    ret = false;
                }
            }
        });
    });
    return ret;
};


/**
 * 목록에서 페이지 이동시 파라메터 저장
 */

lpCom.setSearchCond = function(){
     let param = $("#schFrm").srializeJsonById();
     localStorage.setItem('searchCond', JSON.stringify(param));
     localStorage.setItem('pageUrl', location.pathname);
}

/**
 * 목록페이지 돌아올때 검색조건 파라메터 자동 설정
 */
lpCom.setPageSearchCond = function(){
   let searchCond = localStorage.getItem('searchCond');
    if(searchCond != null ){
        searchCond = JSON.parse(searchCond);
        for(let objId in searchCond ){
            if(!objId.isEmpty()){
                let searchObj = $("#schFrm #"+objId);
                $(searchObj).val(searchCond[objId]);
               }
        }
   }

    localStorage.clear(); //클리어
   //수동설정을 위한 오브젝트 리턴
    return searchCond;
}

/**
 * 레이어 팝업 오픈
 */
lpCom.popupDivOpen = function(url,param,option){
       if(option == undefined) option = {};
       if(option.width == undefined) option.width = "1200";
       if(option.height == undefined) option.height = "720";
       if(option.follow == undefined) option.follow = true;
       $("body div[id=element_to_pop_up]").remove();
       let popDivObj = "<div id='element_to_pop_up' style='display:none;'>"
                    //+"<span class='button b-close' style='border-radius:7px 7px 7px 7px;box-shadow:none;font:bold 131% sans-serif;padding:0 6px 2px;position:absolute;right:-20px;top:-7px; background-color:#2b91af; color:#fff; cursor: pointer; display: inline-block; text-align: center;'><span>X</span></span>"
                    +"<div class='content' style='width:"+option.width+"px;height:"+option.height+"px'></div>";
                    "</div>";

       $("body").append(popDivObj);

       $divPopopParam = param;

       $("#element_to_pop_up").bPopup({
           content:'iframe' //'ajax', 'iframe' or 'image'
         , iframeAttr :'scrolling="auto" frameborder="0" width="100%" height="100%" '
         , contentContainer:".content"
         , follow:[option.follow, option.follow]
         , loadUrl: lpCom.contextPath+url+"?"+lpCom.serializeByJsonData(param) //Uses jQuery.load()
       });
}


/**
 * 레이어 팝업 닫기
 */
lpCom.popupDivClose = function(pSid,pRetParam){

    if(window.parent.calBackPopupFunc != undefined){
        window.parent.calBackPopupFunc(pSid,pRetParam);
    }

    window.parent.$('#element_to_pop_up').bPopup().close();
}

/**
* 레이어 팝업 파라메턴 리턴
*/
lpCom.getParamPopupDiv = function(){

    if(window.parent.$divPopopParam != undefined){
        return window.parent.$divPopopParam;
    }else{
        return {};
    }
}

/**
 *  파일 존재 확인여부
 *
 */
lpCom.fnFileExists = function(fileUrl){

    if(fileUrl){
        let req = new XMLHttpRequest();
        req.open('GET', fileUrl, false);
        req.send();
        return req.status==200;
    } else {
        return false;
   }
}


/**
 * 페이지 readOnly 설정 뷰페이로 보기용
 */
lpCom.setPageReadOnly = function(){
    let $inputObj = $('div[id=wrap] :input').filter('[notReadOnlyTag!=""]');
    $inputObj.each(function(index,item){ //TEXTAREA.INPUT,SELECT
        let objTagName = $(item).get(0).tagName;
        switch(objTagName){
            case "INPUT" :
                     let objType = $(item).attr("type"); //text date radio checkbox
                     if(objType == "text" || objType == "date" || objType == "date1" || objType == "textbox" ){
                         $(item).attr("readonly",true);
                         if((objType == "date" || objType == "date1" || objType == "date2" )){
                            $(item).attr("type","text");
                            $(item).removeClass("cal");
                         }
                     }else{
                         $(item).attr('disabled', true);
                     }
                     break;
            case "TEXTAREA" :
                    $(item).attr("readonly",true);
                break;
            case "SELECT" :
                $(item).attr("readonly",true);
                $(item).find("option").not(":selected").attr("disabled", "disabled");
                break;
          }
    });

    //버튼설정 목록버튼은 기본적으로 보임처리
    let $btnObj = $('a[class^=btn_]').filter('[data-notReadOnly!="true"]').filter('[id!=listBtn]');
    $btnObj.hide();
};

/**
 * 바이트 계산
 * */
lpCom.byteCheck = function(pVal){
    var codeByte = 0;
    for (var idx = 0; idx < pVal.length; idx++) {
        var oneChar = escape(pVal.charAt(idx));
        if ( oneChar.length == 1 ) {
            codeByte ++;
        } else if (oneChar.indexOf("%u") != -1) {
            codeByte += 3; // 한글 3바이트 인식
        } else if (oneChar.indexOf("%") != -1) {
            codeByte ++;
        }
    }
    return codeByte;
}

/**
 * 공통코드 체크박스 설정
 * */
lpCom.setCodeCheckBox = function(pTargetId,pParam){

    let ckData = lpCom.setCodeSelect("",{ mastCd:pParam.mastCd,first:"X"});
    let tagetId = $("#"+pTargetId);
    let tagetVal = $("#"+pTargetId).val();

    let valArray = tagetVal.split(",");

    let objArr = ["<ul>"];
    for(idx in ckData) {
        let check = "";
        objArr.push("<li style='float:left;line-height: 20px;'>");
        if(pParam.initIsAll == "Y" || valArray.indexOf(ckData[idx].cd) > -1 ) check="checked";
        objArr.push("<input onchange=lpCom.codeCheckBoxChg('"+pTargetId+"') type='checkbox' id='"+ckData[idx].cd+"' name = '"+pTargetId+"_CK' "+check+"/> ")
        objArr.push("<label for='"+ckData[idx].cd+"' style='margin-right:18px;'>"+ckData[idx].cdNm+"</label>")
        objArr.push("</li>")
    }

    objArr.push("</ul>")

    tagetId.after(objArr.join(""));


    if(pParam.initIsAll == "Y") $($(":input[NAME="+pTargetId+"_CK]")[0]).change(); //초기에 전체 설정시 값 설정함
}

/**
 * 공통코드 체크박스 설정 변경 이벤트
 * */
lpCom.codeCheckBoxChg = function(pTargetId){

    let allVal = [];
    let $ckObj =  $(":input[NAME="+pTargetId+"_CK]")
    $ckObj.each(function(index,item){
           if($(item).is(":checked")){
               allVal.push($(item).attr("id"));
           }
      });

    $("#"+pTargetId).val(allVal);
}


lpCom.serializeByJsonData = function(pParam){
    let ret = "";
    for(let key in pParam ){
        ret += "&"+key+"="+pParam[key];
    }

    return ret.substring(1);
}

//파일 다운로드 a 태크 생성후 다운로드 (파일 여러개 다운르도 사용시)
lpCom.fileDownObjCreate =  function(pHref){
    let element = document.createElement('a');
    element.setAttribute('href', pHref);
    element.setAttribute('download', "파일다운");
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
}

//컨텐츠 레이어 삽입
lpCom.loadLayer = function(pTargetId , pUrl, pParam) {

    if(pParam == undefined) pParam = {};
    if(!lpCom.isEmpty($("#"+pTargetId).html())) return;

    $.ajax({
         url : lpCom.contextPath + pUrl,
         async : false,
         data : pParam,
         success : function (data) {
             $("#"+pTargetId).append(data);
             $("#"+pTargetId).after("<div class='dim'></div>");  //background
             $('.dim').show();
             $("#"+pTargetId).fadeIn(100);

             lpCom.init("#"+pTargetId);

         },
         error:function(request,status,error){
            alert(error);
         }
     });
};

//컨텐츠 레이어 삭제
lpCom.closeLayer = function(pTargetId, pRetParam) {

    $("#"+pTargetId).html("");
    $("#"+pTargetId).fadeOut();
    $("#"+pTargetId).next(".dim").remove();

    if(window.calBackPopupFunc != undefined){
        window.calBackPopupFunc(pTargetId, pRetParam);
    }
};

/**
 * 사업자 등록번호 체크
 * */
lpCom.checkBsnsNmbr = function(number) {
    let numberMap = number.replace(/-/gi, '').split('').map(function (d){
        return parseInt(d, 10);
    });

    if(numberMap.length == 10){
        let keyArr = [1, 3, 7, 1, 3, 7, 1, 3, 5];
        let chk = 0;

        keyArr.forEach(function(d, i){
            chk += d * numberMap[i];
        });

        chk += parseInt((keyArr[8] * numberMap[8])/ 10, 10);
        return Math.floor(numberMap[9]) === ( (10 - (chk % 10) ) % 10);
    }
    return false;
}


/**
 * 핸드폰번호 체크
 * */
lpCom.checkPhoneNumber = function(tel) {
    var trans_num = tel.val().replace(/-/gi,'');
    var regExp_ctn = /^(01[016789]{1}|02|0[3-9]{1}[0-9]{1})([0-9]{3,4})([0-9]{4})$/;

    if(regExp_ctn.test(trans_num) && (trans_num.length==11 || trans_num.length==10)) {

        trans_num = trans_num.replace(/^(01[016789]{1}|02|0[3-9]{1}[0-9]{1})-?([0-9]{3,4})-?([0-9]{4})$/, "$1-$2-$3");
        tel.val(trans_num);

        return true;
    } else {
        return false;
    }
    return false;
}

/*
 * 데이터 단위 변환
 */
lpCom.formatBytes = function(bytes) {
      if (bytes === 0) return '0 Bytes';
      const k = 1024;
      const sizes = ['Bytes', 'KB', 'MB', 'GB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(0)) + ' ' + sizes[i];
  }

  /**
   * uuid
   */
lpCom.getUuid = function() {
    if (window.crypto && window.crypto.getRandomValues) {
        var array = new Uint8Array(16);
        window.crypto.getRandomValues(array);
        array[6] = (array[6] & 0x0f) | 0x40; // UUID version 4
        array[8] = (array[8] & 0x3f) | 0x80; // UUID variant

        return [...array].map((b, i) => {
            return (i === 4 || i === 6 || i === 8 || i === 10 ? '-' : '') +
                   b.toString(16).padStart(2, '0');
        }).join('');
    }
}



/**
 * 엑셀 다운로드
 *
 * @param {string} pFileNm : 파일명
 * @param {string} pUrl :  url
 * @param {string} pParamMap : 조회 parameter
 * @param {json} pColumnLayout : auigrid columnLayout 정보
 * @param {json} pOption : 옵션
 */
lpCom.AjaxExcel = function(pFileNm, pUrl, pParamMap, pColumnLayout, pOption) {

    if (lpCom.isEmpty(pOption)) {
        pOption = {};
        pOption.width = 60;  //그리드 컬럼 너비 60%만
    }

    let lpComInner = {};
    lpComInner.excelInnerCallBack = function(pSid,pData){

        let pCols = {};
        let pWidth = {};

        pColumnLayout = lpAuiGrid.flatGridData(pColumnLayout);
        for(let idx in pColumnLayout) {
            let excelRowData = pColumnLayout[idx];

            if(!excelRowData.hasOwnProperty("dataField")) continue;
            pCols[excelRowData.dataField] = excelRowData.headerText.replaceAll("<br>","").replaceAll("<BR>","");
            pWidth[excelRowData.dataField] = (Math.round(Number(excelRowData.width) * pOption.width ) / 100);  //그리드 컬럼 너비
        }
        lpAuiGrid.flatGridData(StdGrid.gridParam.columnLayout)


        let option = {};
        option.title = pFileNm;
        option.fileNm = pFileNm;
        option.width = pWidth;

        lpCom.downExcel(pData.retList, pCols, option);
        lpComInner.excelInnerCallBack = null; //메모리 누수 방지
    }

    pParamMap.excelDownAt = "Y";
    let otherInit = {};
    otherInit.isSuccesMsg = false;
    pParamMap.rowCountPage = "999999";
    lpCom.Ajax(pFileNm,pUrl, pParamMap, lpComInner.excelInnerCallBack,otherInit);
};



/**
 * 엑셀 다운로드
 * @param {json} rowData : json 출력 데이터
 * @param {json} pCols : 엑셀 표현할 컬럼  let pCols = {col1:"사용자",col2:"이름"}
 * @param {json} pOption : 엑셀 타이틀, 파일명, 컬럼 너비  let pOption = {title:"sample",fileNm:"sample", width = {col2:200}}
 */
lpCom.downExcel = function(rowData, pCols, pOption) {

    if(lpCom.isEmpty(rowData)) {
        alert("데이터가 없습니다.");
        return;
    };

    if(!pOption.hasOwnProperty("title")) pOption.title = "";  //title
    if(!pOption.hasOwnProperty("fileNm")) pOption.fileNm = "";  //파일명
    if(!pOption.hasOwnProperty("width")) pOption.width = {};  //컬럼 너비

    let tmpData = {};
    let keys = Object.keys(rowData[0]);

    $.each(keys, function(index, key) {
        tmpData[key] = pCols[key];
    });
    rowData.unshift(tmpData);  //제목 추가

    let excelDatas = [];
    let excelData = {};

    let colsKeys = Object.keys(pCols);
    let wpxs = [];

    $.each(colsKeys, function(index, key) {
        excelData[key] = pCols[key];

        //컬럼너비 개별 설정, 없으면 기본 80
        let wd = lpCom.isEmpty(pOption.width[key]) ? 80 : pOption.width[key];
        wpxs.push({wpx:wd});  //col 너비
    });

    //정의된 데이터 목록으로 다시 세팅
    for(idx in rowData){
        let tmpData = {};
        let subData = rowData[idx];
        $.each(colsKeys, function(i, key) {
            if(rowData[idx].hasOwnProperty(key)) {
                tmpData[key] = subData[key];
            }
        });
        excelDatas.push(tmpData);
    };

    // 워크시트 생성 (JSON 형식)
    const ws = XLSX.utils.json_to_sheet(excelDatas, { skipHeader: true });
    //const ws = XLSX.utils.table_to_sheet(table);  워크시트 생성 (table 형식)

    ws['!cols'] = wpxs;  //컬럼 너비 설정

    //컬럼 헤더 스타일
    const range = XLSX.utils.decode_range(ws['!ref']);
    for(let col = range.s.c; col <= range.e.c; col++) {
        const cellAddress = XLSX.utils.encode_cell({r: 0, c: col}); // 첫번째 행, 열 이동
        ws[cellAddress].s = {
            font: {
                sz: 11
            }
            , fill: {
                fgColor: { rgb: "d4d4d4" } // 회색 배경 설정
            }
            , border: {
                top:    { style: "thin", color: { rgb: "000000" } }, // 위쪽 테두리
                bottom: { style: "thin", color: { rgb: "000000" } }, // 아래쪽 테두리
            }
        };
    }

    ws['!rows'] = [{ hpt: 20 }];  // 첫 번째 행의 높이를 20 포인트로 설정

    // 워크북 생성
    const wb = XLSX.utils.book_new();

    // 워크북에 워크시트 추가
    XLSX.utils.book_append_sheet(wb, ws, "Sheet1");

    let dt = lpCom.getCurrentDate("")+lpCom.getCurrentTime("");  //파일명 날짜

    let fimeNm = (lpCom.isEmpty(pOption.fileNm)) ? "" : pOption.fileNm+"_";
    fimeNm = fimeNm.replace(" ","_") + dt + ".xlsx"

    // 엑셀 파일 저장
    XLSX.writeFile(wb, fimeNm);
};

/**
 * 파일다운로드 Ajax 통신
 * DESC : iframe submit을 한후. iframe의 요청후의 생성된 쿠키를 이용해서 처리
 *      : fileDownload.js 플러그인 사용
 *        -> 서버 response.setHeader("Set-Cookie", "fileDownload=true or false;");
 */
lpCom.fileDownAjax = function(pUrl, pParam){

    if(!pParam.hasOwnProperty("lodingImg")) pParam.lodingImg = true;

    var _lodingDiv = lpCom.loadingDivCreate();
    if(pParam.lodingImg) window.top.document.body.appendChild(_lodingDiv);  //로딩 이미지 생성

    var ajaxSetup = {
            data : pParam
            , successCallback: function() {
                if(pParam.lodingImg) window.top.document.body.removeChild(_lodingDiv); //로딩 이미지 제거
            }
            , failCallback  : function() {
                if(pParam.lodingImg) window.top.document.body.removeChild(_lodingDiv); //로딩 이미지 제거
                alert("다운로드중.오류가 발생하였습니다.");
            }
        };

    $.fileDownload(pUrl, ajaxSetup);

};
